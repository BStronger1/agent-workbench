package io.github.bstronger1.workbench;

import jakarta.annotation.PreDestroy;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import java.util.*;
import java.util.concurrent.*;
import static io.github.bstronger1.workbench.Domain.*;

@Service
public class WorkflowEngine {
    private final ProjectStore store;
    private final MemoryService memory;
    private final GenerationModel model;
    private final ArtifactValidator validator;
    private final String mode;
    private final double inputPrice, outputPrice;
    private final ThreadPoolExecutor executor = new ThreadPoolExecutor(2, 2, 0, TimeUnit.SECONDS, new ArrayBlockingQueue<>(12));
    public WorkflowEngine(ProjectStore store, MemoryService memory, GenerationModel model, ArtifactValidator validator,
                          @Value("${workbench.mode}") String mode, @Value("${workbench.input-price}") double inputPrice,
                          @Value("${workbench.output-price}") double outputPrice) {
        if (!Set.of("demo", "live").contains(mode)) throw new IllegalArgumentException("模式必须为 demo 或 live");
        this.store = store; this.memory = memory; this.model = model; this.validator = validator;
        this.mode = mode; this.inputPrice = inputPrice; this.outputPrice = outputPrice;
    }
    public String mode() { return mode; }
    public Run submit(String owner, String projectId, GenerateRequest request) {
        return submit(owner, projectId, request, null);
    }
    public Run submit(String owner, String projectId, GenerateRequest request, ProviderSettings.Credentials credentials) {
        Project p = store.get(owner, projectId);
        if (p.runs.size() >= 50) throw new IllegalArgumentException("项目运行记录达到上限，请新建项目");
        if (p.runs.stream().anyMatch(r -> Set.of("RUNNING", "QUEUED").contains(r.status))) throw new IllegalArgumentException("项目已有运行中的任务");
        Run r = new Run(); r.prompt = Api.requireText(request.prompt(), 2000);
        r.maxRepairs = request.maxRepairs() == null ? 2 : request.maxRepairs();
        r.tokenBudget = request.tokenBudget() == null ? 24000 : request.tokenBudget();
        if (r.maxRepairs < 0 || r.maxRepairs > 3 || r.tokenBudget < 1000 || r.tokenBudget > 50000) throw new IllegalArgumentException("修复次数或预算超出范围");
        r.requiredTexts = request.requiredTexts() == null ? List.of() : request.requiredTexts().stream().map(t -> Api.requireText(t, 100)).distinct().toList();
        if (r.requiredTexts.size() > 8) throw new IllegalArgumentException("最多设置 8 条文本验收");
        r.checkInteraction = !Boolean.FALSE.equals(request.checkInteraction());
        r.memoryStrategy = request.memoryStrategy() == null ? "retrieval" : request.memoryStrategy();
        if (!Set.of("none", "window", "retrieval").contains(r.memoryStrategy)) throw new IllegalArgumentException("未知记忆策略");
        r.mode = credentials == null ? mode : "live";
        r.model = credentials != null ? credentials.model() : mode.equals("demo") ? "deterministic-template-v1" : model.name();
        r.memorySources = memory.context(p, r.prompt, r.memoryStrategy);
        if (r.mode.equals("live") && credentials == null && !model.configured()) throw new IllegalArgumentException("请先填写模型配置");
        store.update(owner, projectId, project -> {
            if (project.runs.stream().anyMatch(x -> Set.of("RUNNING", "QUEUED").contains(x.status))) throw new IllegalArgumentException("项目已有运行中的任务");
            project.runs.add(r); return null;
        });
        try { executor.execute(() -> executeWithCredentials(owner, projectId, r, Boolean.TRUE.equals(request.demoFailure()), credentials)); }
        catch (RejectedExecutionException e) { finish(owner, projectId, r, "FAILED", "任务队列已满，请稍后重试"); }
        return r;
    }
    void execute(String owner, String projectId, Run r, boolean demoFailure) {
        executeWithCredentials(owner, projectId, r, demoFailure, null);
    }
    void executeWithCredentials(String owner, String projectId, Run r, boolean demoFailure, ProviderSettings.Credentials credentials) {
        long start = System.nanoTime(); r.status = "RUNNING";
        event(owner, projectId, r, "memory", "已选取 " + r.memorySources.size() + " 条来源（" + r.memoryStrategy + "）");
        String html = null; List<String> errors = List.of();
        try {
            for (int i = 0; i <= r.maxRepairs; i++) {
                if (Thread.currentThread().isInterrupted()) throw new InterruptedException();
                // Conservative upper bound, not a tokenizer: UTF-8 bytes bound input tokens for supported byte BPE models.
                int inputBound = (r.prompt + r.memorySources + (html == null ? "" : html) + errors + r.requiredTexts)
                        .getBytes(java.nio.charset.StandardCharsets.UTF_8).length + 2048;
                if (r.mode.equals("live") && (!r.usageKnown || r.inputTokens + r.outputTokens + inputBound + 4096 > r.tokenBudget)) {
                    r.status = "BUDGET_EXCEEDED"; r.error = "保守预算检查停止了后续调用；可提高预算后重试。"; break;
                }
                event(owner, projectId, r, i == 0 ? "generate" : "repair", i == 0 ? "开始生成" : "根据验收失败原因修复，第 " + i + " 轮");
                long attemptStart = System.nanoTime();
                ModelReply reply = credentials == null ? model.generate(r, html, errors, demoFailure && i == 0)
                        : model.generate(r, html, errors, demoFailure && i == 0, credentials);
                html = reply.html(); r.inputTokens += reply.inputTokens(); r.outputTokens += reply.outputTokens(); r.usageKnown &= reply.usageKnown();
                event(owner, projectId, r, "validate", "检查结构、资源边界及浏览器交互");
                var validation = validator.validate(html, r, i); errors = validation.errors();
                r.attempts.add(new Attempt(i, html, errors, validation.browserStatus(), validation.screenshot(), (System.nanoTime() - attemptStart) / 1_000_000));
                if (errors.isEmpty()) { r.status = validation.browserStatus().equals("PASSED") ? "PASSED" : "STATIC_VALIDATED"; break; }
                if (validation.browserStatus().equals("ERROR")) { r.status = "FAILED"; r.error = "验收基础设施异常，已停止，未当作代码缺陷重试。"; break; }
                if (i == r.maxRepairs) { r.status = "FAILED"; r.error = "达到修复次数上限，仍未通过验收。"; }
            }
        } catch (Exception e) {
            r.status = "FAILED"; r.error = e instanceof IllegalStateException ? e.getMessage() : "生成或验收失败，请检查服务器配置后重试。";
        } finally {
            r.durationMs = (System.nanoTime() - start) / 1_000_000;
            if (r.mode.equals("demo")) r.estimatedCost = 0.0;
            else {
                double in = credentials == null ? inputPrice : credentials.inputPrice(), out = credentials == null ? outputPrice : credentials.outputPrice();
                if (r.usageKnown && in > 0 && out > 0) r.estimatedCost = (r.inputTokens * in + r.outputTokens * out) / 1_000_000;
            }
            finish(owner, projectId, r, r.status, r.error);
        }
    }
    private void event(String owner, String projectId, Run r, String stage, String message) {
        r.events.add(new Event(now(), stage, message)); save(owner, projectId, r);
    }
    private void save(String owner, String projectId, Run r) {
        store.update(owner, projectId, p -> { p.runs.removeIf(old -> old.id.equals(r.id)); p.runs.add(r); return null; });
    }
    private void finish(String owner, String projectId, Run r, String status, String error) {
        r.status = status; r.error = error; r.completedAt = now(); r.events.add(new Event(now(), "complete", status));
        store.update(owner, projectId, p -> {
            p.runs.removeIf(old -> old.id.equals(r.id)); p.runs.add(r);
            if (Set.of("PASSED", "STATIC_VALIDATED").contains(status)) p.selectedRunId = r.id;
            return null;
        });
    }
    @PreDestroy public void stop() { executor.shutdownNow(); }
}
