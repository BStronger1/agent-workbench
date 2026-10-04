package io.github.bstronger1.workbench;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.jsoup.Jsoup;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import java.nio.file.*;
import java.util.*;
import java.util.concurrent.TimeUnit;
import static io.github.bstronger1.workbench.Domain.*;

@Component
public class ArtifactValidator {
    public static final String CSP = "sandbox allow-scripts; default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data:; font-src data:; connect-src 'none'; form-action 'none'; base-uri 'none'";
    private final String qaCommand;
    private final ProjectStore store;
    private final ObjectMapper mapper;
    public ArtifactValidator(@Value("${workbench.qa-command}") String qaCommand, ProjectStore store, ObjectMapper mapper) {
        this.qaCommand = qaCommand; this.store = store; this.mapper = mapper;
    }
    public boolean browserEnabled() { return !qaCommand.isBlank(); }
    public record Validation(List<String> errors, String browserStatus, String screenshot) {}
    public Validation validate(String html, Run run, int attempt) throws Exception {
        List<String> errors = new ArrayList<>(staticErrors(html, run.requiredTexts, run.checkInteraction));
        if (!errors.isEmpty()) return new Validation(errors, "NOT_RUN", null);
        if (!browserEnabled()) return new Validation(List.of(), "NOT_CONFIGURED", null);
        Path task = store.root().resolve("qa").resolve(run.id).resolve("attempt-" + attempt);
        Files.createDirectories(task);
        Files.writeString(task.resolve("index.html"), html);
        mapper.writeValue(task.resolve("contract.json").toFile(), Map.of("requiredTexts", run.requiredTexts, "checkInteraction", run.checkInteraction));
        // Command is a server-owned JSON argv array, never a model-generated command or shell expression.
        List<String> command = new ArrayList<>(Arrays.asList(mapper.readValue(qaCommand, String[].class)));
        command.add(task.toString());
        Process process = new ProcessBuilder(command).redirectErrorStream(true).redirectOutput(task.resolve("worker.log").toFile()).start();
        if (!process.waitFor(45, TimeUnit.SECONDS)) {
            process.descendants().forEach(ProcessHandle::destroyForcibly); process.destroyForcibly();
            return new Validation(List.of("浏览器验收超时"), "ERROR", null);
        }
        if (process.exitValue() != 0 || !Files.isRegularFile(task.resolve("result.json")))
            return new Validation(List.of("浏览器验收服务不可用"), "ERROR", null);
        var result = mapper.readTree(task.resolve("result.json").toFile());
        result.path("errors").forEach(e -> errors.add(e.asText()));
        return new Validation(errors, errors.isEmpty() ? "PASSED" : "FAILED", Files.exists(task.resolve("screenshot.png")) ? run.id + "/attempt-" + attempt + "/screenshot.png" : null);
    }
    public static List<String> staticErrors(String html, List<String> required, boolean interaction) {
        List<String> errors = new ArrayList<>();
        if (html == null || html.isBlank() || html.length() > 150_000) return new ArrayList<>(List.of("HTML 为空或超过大小限制"));
        var doc = Jsoup.parse(html);
        if (!html.toLowerCase(Locale.ROOT).contains("<!doctype html")) errors.add("缺少 HTML doctype");
        if (doc.title().isBlank()) errors.add("缺少页面标题");
        if (doc.select("h1").isEmpty()) errors.add("缺少一级标题");
        if (doc.select("meta[name=viewport]").isEmpty()) errors.add("缺少移动端 viewport");
        if (!doc.select("iframe,object,embed,form,base,meta[http-equiv],link,script[src]").isEmpty()) errors.add("含不支持的外部资源或嵌入标签");
        for (var e : doc.select("[src],[href],[action]")) for (String attr : List.of("src", "href", "action")) {
            String value = e.attr(attr).trim();
            if (!value.isEmpty() && !value.startsWith("#") && !(attr.equals("src") && e.tagName().equals("img") && value.startsWith("data:image/"))) errors.add("资源必须内联：" + attr);
        }
        for (String text : required) if (!doc.body().text().contains(text)) errors.add("缺少验收文本：" + text);
        if (interaction && (doc.select("button[data-testid=primary-action]").isEmpty() || doc.select("[data-testid=result]").isEmpty())) errors.add("缺少交互验收元素");
        return errors.stream().distinct().toList();
    }
}
