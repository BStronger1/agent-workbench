package io.github.bstronger1.workbench;

import com.fasterxml.jackson.databind.*;
import org.springframework.stereotype.Component;
import org.springframework.beans.factory.annotation.Value;
import java.net.URI;
import java.net.http.*;
import java.time.Duration;
import java.util.*;
import static io.github.bstronger1.workbench.Domain.*;

@Component
public class AiClient {
    private final String url, token;
    private final ObjectMapper mapper;
    private final HttpClient http = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(3)).build();
    public AiClient(ObjectMapper mapper,@Value("${workbench.ai-url:}") String url,@Value("${workbench.ai-token:}") String token) {
        this.mapper=mapper;this.url=url;this.token=token;
        if (!url.isBlank() && (!url.matches("http://127\\.0\\.0\\.1:[0-9]{2,5}") || token.length()<32))
            throw new IllegalArgumentException("AI 服务仅支持带内部口令的本机地址");
    }
    public boolean enabled() { return !url.isBlank(); }
    public JsonNode post(String path,Object body) {
        if (!enabled()) throw new IllegalArgumentException("AI 服务尚未启用");
        try {
            var request=HttpRequest.newBuilder(URI.create(url+path)).timeout(Duration.ofMinutes(20))
                .header("X-AI-Token",token).header("Content-Type","application/json")
                .POST(HttpRequest.BodyPublishers.ofString(mapper.writeValueAsString(body))).build();
            var response=http.send(request,HttpResponse.BodyHandlers.ofString());
            if(response.statusCode()!=200) throw new IllegalStateException("AI 服务请求失败（HTTP "+response.statusCode()+"），请检查服务配置");
            if(response.body().length()>2_000_000) throw new IllegalStateException("AI 响应过大");
            return mapper.readTree(response.body());
        } catch(IllegalStateException e) {throw e;} catch(Exception e) {throw new IllegalStateException("AI 服务未响应；任务保留，可检查服务后恢复");}
    }
    public JsonNode knowledge(Project p,String query,boolean answer,ProviderSettings.Credentials credentials) {
        Map<String,Object> body=new LinkedHashMap<>();
        body.put("owner",p.owner);body.put("projectId",p.id);body.put("query",query);
        body.put("memories",p.memories);body.put("documents",p.documents);body.put("answer",answer);
        if(credentials!=null)body.put("credentials",credentials);
        return post("/knowledge",body);
    }
    public void execute(String owner,String projectId,Run r,ProviderSettings.Credentials credentials,boolean resume) {
        Map<String,Object> body=new LinkedHashMap<>();
        body.put("owner",owner);body.put("projectId",projectId);body.put("runId",r.id);body.put("prompt",r.prompt);
        body.put("workflow",r.workflow);body.put("contract",Map.of("requiredTexts",r.requiredTexts,"checkInteraction",r.checkInteraction,"steps",r.steps));
        body.put("sources",r.memorySources);body.put("maxRepairs",r.maxRepairs);body.put("tokenBudget",r.tokenBudget);
        body.put("pauseAfterPlan",r.pauseAfterPlan);body.put("resume",resume);body.put("credentials",credentials);
        var result=post("/runs",body);
        r.status=result.path("status").asText("INTERRUPTED");r.error=result.path("error").asText();
        r.resumable=result.path("resumable").asBoolean();r.contractHash=result.path("contractHash").asText();
        r.calls=result.path("calls").asInt();r.durationMs=result.path("durationMs").asLong();
        r.inputTokens=result.path("inputTokens").asInt();r.outputTokens=result.path("outputTokens").asInt();r.usageKnown=result.path("usageKnown").asBoolean(false);
        if(result.has("attempts"))r.attempts=new ArrayList<>(Arrays.asList(mapper.convertValue(result.get("attempts"),Attempt[].class)));
        if(result.has("events"))r.events=new ArrayList<>(Arrays.asList(mapper.convertValue(result.get("events"),Event[].class)));
        if(result.has("plan"))r.plan=mapper.convertValue(result.get("plan"),Map.class);
        if(result.path("contract").has("steps"))r.steps=new ArrayList<>(Arrays.asList(mapper.convertValue(result.path("contract").get("steps"),Step[].class)));
    }
    public List<Source> sources(JsonNode result) {return Arrays.asList(mapper.convertValue(result.path("sources"),Source[].class));}
}