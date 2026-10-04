package io.github.bstronger1.workbench;

import jakarta.servlet.http.*;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.*;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.server.ResponseStatusException;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.security.MessageDigest;
import java.util.*;
import static io.github.bstronger1.workbench.Domain.*;

@RestController
@RequestMapping("/api/workbench")
public class Api {
    private final ProjectStore store;
    private final MemoryService memory;
    private final WorkflowEngine engine;
    private final ArtifactValidator validator;
    private final GenerationModel model;
    private final String accessToken;
    private final ProviderSettings providers;
    public Api(ProjectStore store, MemoryService memory, WorkflowEngine engine, ArtifactValidator validator,
               GenerationModel model, @Value("${workbench.live-access-token}") String accessToken, ProviderSettings providers) {
        this.store = store; this.memory = memory; this.engine = engine; this.validator = validator; this.model = model; this.accessToken = accessToken;
        this.providers = providers;
    }
    @GetMapping("/config") public Map<String, Object> config(HttpServletRequest req, HttpServletResponse res) {
        String owner = owner(req, res);
        var personal = providers.active(owner);
        return Map.of("name", "Agent Workbench", "mode", personal != null ? "live" : engine.mode(), "modelConfigured", personal != null || model.configured(),
                "browserValidation", validator.browserEnabled(), "liveAccessRequired", personal == null && engine.mode().equals("live"),
                "providerSource", personal != null ? "personal" : engine.mode().equals("live") ? "server" : "demo",
                "scope", "Self-contained HTML apps · lexical project retrieval · source-grounded reports");
    }
    @GetMapping("/provider") public ProviderSettings.View provider(HttpServletRequest req, HttpServletResponse res) {
        return providers.view(owner(req, res));
    }
    @PostMapping("/provider") public ProviderSettings.View saveProvider(@RequestBody ProviderSettings.Input body, HttpServletRequest req, HttpServletResponse res) {
        return providers.save(owner(req, res), body);
    }
    @DeleteMapping("/provider") public Map<String, Boolean> clearProvider(HttpServletRequest req, HttpServletResponse res) {
        providers.clear(owner(req, res)); return Map.of("cleared", true);
    }
    @PostMapping("/provider/test") public Map<String, Object> testProvider(HttpServletRequest req, HttpServletResponse res) {
        var credentials = providers.active(owner(req, res));
        if (credentials == null) throw new IllegalArgumentException("请先保存并启用模型配置");
        try { model.testConnection(credentials); return Map.of("ok", true, "message", "连接测试成功", "model", credentials.model()); }
        catch (IllegalStateException e) { throw new IllegalArgumentException(e.getMessage()); }
        catch (Exception e) { throw new IllegalArgumentException("连接测试失败或超时，请检查服务商配置"); }
    }
    @GetMapping("/projects") public List<Project> list(HttpServletRequest req, HttpServletResponse res) {
        return store.list(owner(req, res)).stream().map(this::publicProject).toList();
    }
    @PostMapping("/projects") public Project create(@RequestBody Map<String, String> body, HttpServletRequest req, HttpServletResponse res) {
        return publicProject(store.create(owner(req, res), requireText(body.get("name"), 80)));
    }
    @GetMapping("/projects/{id}") public Project project(@PathVariable String id, HttpServletRequest req, HttpServletResponse res) {
        return publicProject(store.get(owner(req, res), id));
    }
    @PostMapping("/projects/{id}/memories") public Project remember(@PathVariable String id, @RequestBody Map<String, String> body, HttpServletRequest req, HttpServletResponse res) {
        String owner = owner(req, res);
        store.update(owner, id, p -> memory.remember(p, requireText(body.get("kind"), 20), requireText(body.get("key"), 80), requireText(body.get("value"), 1500)));
        return publicProject(store.get(owner, id));
    }
    @DeleteMapping("/projects/{id}/memories/{memoryId}") public Project forget(@PathVariable String id, @PathVariable String memoryId, HttpServletRequest req, HttpServletResponse res) {
        String owner = owner(req, res);
        store.update(owner, id, p -> { Memory m = p.memories.stream().filter(x -> x.id.equals(memoryId)).findFirst().orElseThrow(); m.active = false; return null; });
        return publicProject(store.get(owner, id));
    }
    @PostMapping("/projects/{id}/documents") public Project document(@PathVariable String id, @RequestBody Map<String, String> body, HttpServletRequest req, HttpServletResponse res) {
        String owner = owner(req, res);
        String title = requireText(body.get("title"), 100), content = requireText(body.get("content"), 30000);
        store.update(owner, id, p -> { if (p.documents.size() >= 20) throw new IllegalArgumentException("最多保存 20 份资料"); p.documents.add(new Document(Domain.id(), title, content, now())); return null; });
        return publicProject(store.get(owner, id));
    }
    @GetMapping("/projects/{id}/knowledge") public Map<String, Object> knowledge(@PathVariable String id, @RequestParam String q, HttpServletRequest req, HttpServletResponse res) {
        Project p = store.get(owner(req, res), id);
        var sources = memory.retrieve(p, requireText(q, 1000), true);
        return Map.of("method", "lexical-extractive", "sources", sources,
                "answer", sources.isEmpty() ? "未找到匹配资料。请补充文档或换用更具体的关键词。" : "以下是检索到的原文证据；未调用模型进行推断。\n\n" + sources.stream().map(s -> "[" + s.id() + "] " + s.excerpt()).reduce((a,b) -> a + "\n\n" + b).orElse(""));
    }
    @PostMapping("/projects/{id}/runs") public Run run(@PathVariable String id, @RequestBody GenerateRequest body, HttpServletRequest req, HttpServletResponse res) {
        String owner = owner(req, res);
        var credentials = providers.active(owner);
        if (credentials == null && engine.mode().equals("live")) {
            String supplied = Objects.toString(req.getHeader("X-Live-Access"), "");
            if (accessToken.length() < 24 || !MessageDigest.isEqual(accessToken.getBytes(StandardCharsets.UTF_8), supplied.getBytes(StandardCharsets.UTF_8)))
                throw new ResponseStatusException(HttpStatus.FORBIDDEN, "真实模型调用需要工作台访问口令");
        }
        return engine.submit(owner, id, body, credentials);
    }
    @PostMapping("/projects/{id}/select/{runId}") public Project select(@PathVariable String id, @PathVariable String runId, HttpServletRequest req, HttpServletResponse res) {
        String owner = owner(req, res);
        store.update(owner, id, p -> { Run r = findRun(p, runId); if (!Set.of("PASSED", "STATIC_VALIDATED").contains(r.status)) throw new IllegalArgumentException("只能回退到通过验收的版本"); p.selectedRunId = r.id; return null; });
        return publicProject(store.get(owner, id));
    }
    @GetMapping(value="/projects/{id}/runs/{runId}/artifact", produces="text/html;charset=UTF-8")
    public ResponseEntity<String> artifact(@PathVariable String id, @PathVariable String runId, HttpServletRequest req, HttpServletResponse res) {
        Run r = findRun(store.get(owner(req, res), id), runId);
        if (r.attempts.isEmpty()) throw new NoSuchElementException();
        return ResponseEntity.ok().header("Content-Security-Policy", ArtifactValidator.CSP).header("X-Content-Type-Options", "nosniff")
                .header("Cache-Control", "no-store").body(r.attempts.getLast().html());
    }
    @GetMapping("/projects/{id}/runs/{runId}/screenshot/{attempt}")
    public ResponseEntity<byte[]> screenshot(@PathVariable String id, @PathVariable String runId, @PathVariable int attempt, HttpServletRequest req, HttpServletResponse res) throws Exception {
        Run r = findRun(store.get(owner(req, res), id), runId);
        if (attempt < 0 || attempt >= r.attempts.size() || r.attempts.get(attempt).screenshot() == null) throw new NoSuchElementException();
        Path path = store.root().resolve("qa").resolve(r.attempts.get(attempt).screenshot()).normalize();
        if (!path.startsWith(store.root().resolve("qa"))) throw new NoSuchElementException();
        return ResponseEntity.ok().contentType(MediaType.IMAGE_PNG).header("Cache-Control", "no-store").body(Files.readAllBytes(path));
    }
    @GetMapping(value="/projects/{id}/report", produces="text/markdown;charset=UTF-8")
    public String report(@PathVariable String id, HttpServletRequest req, HttpServletResponse res) {
        Project p = store.get(owner(req, res), id);
        StringBuilder out = new StringBuilder("# " + p.name + "\n\n生成时间：" + now() + "\n\n本报告由项目记录确定性整理，演示运行不代表真实模型表现。\n\n## 需求与决策\n\n");
        for (Memory m : p.memories) if (m.active) out.append("- ").append(m.key).append("：").append(m.value).append(" [").append(m.id).append("]\n");
        out.append("\n## 来源资料\n\n");
        for (Document d : p.documents) out.append("- ").append(d.title()).append(" [").append(d.id()).append("]\n");
        out.append("\n## 运行证据\n\n| 运行 | 模式 | 状态 | 尝试次数 | 耗时 ms | Token |\n|---|---|---|---:|---:|---:|\n");
        for (Run r : p.runs) out.append("| ").append(r.id).append(" | ").append(r.mode).append(" | ").append(r.status).append(" | ").append(r.attempts.size()).append(" | ").append(r.durationMs).append(" | ").append(r.usageKnown ? r.inputTokens + r.outputTokens : "未返回").append(" |\n");
        out.append("\n## 汇报提纲\n\n1. 用户问题与验收标准\n2. 项目约束及来源\n3. 生成、检查和修复过程\n4. 效果与失败案例\n5. 已知限制与下一步\n");
        return out.toString();
    }
    private Project publicProject(Project p) { p.owner = null; return p; }
    static Run findRun(Project p, String id) { return p.runs.stream().filter(r -> r.id.equals(id)).findFirst().orElseThrow(); }
    public static String requireText(String text, int max) {
        if (text == null || text.isBlank() || text.length() > max) throw new IllegalArgumentException("文本不能为空且不能超过 " + max + " 字符");
        return text.trim();
    }
    private String owner(HttpServletRequest req, HttpServletResponse res) {
        res.setHeader("Cache-Control", "no-store");
        if (!req.getMethod().equals("GET")) {
            if (!"workbench".equals(req.getHeader("X-Requested-With")) || "cross-site".equals(req.getHeader("Sec-Fetch-Site")))
                throw new ResponseStatusException(HttpStatus.FORBIDDEN, "请求来源校验失败");
        }
        String token = null;
        if (req.getCookies() != null) for (Cookie c : req.getCookies()) if (c.getName().equals("wb_owner") && c.getValue().matches("[a-f0-9]{64}")) token = c.getValue();
        if (token == null) {
            token = UUID.randomUUID().toString().replace("-", "") + UUID.randomUUID().toString().replace("-", "");
            res.addHeader("Set-Cookie", ResponseCookie.from("wb_owner", token).path("/").httpOnly(true).sameSite("Lax").secure(req.isSecure()).maxAge(31536000).build().toString());
        }
        try { return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(token.getBytes(StandardCharsets.UTF_8))); }
        catch (Exception e) { throw new IllegalStateException(e); }
    }
    @ExceptionHandler({IllegalArgumentException.class, NoSuchElementException.class, ResponseStatusException.class})
    public ResponseEntity<Map<String,String>> invalid(Exception e) {
        int code = e instanceof NoSuchElementException ? 404 : e instanceof ResponseStatusException r ? r.getStatusCode().value() : 400;
        return ResponseEntity.status(code).body(Map.of("message", e instanceof ResponseStatusException r ? Objects.toString(r.getReason(), "请求失败") : Objects.toString(e.getMessage(), "记录不存在")));
    }
}
