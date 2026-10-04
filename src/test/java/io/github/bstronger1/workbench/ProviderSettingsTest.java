package io.github.bstronger1.workbench;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.*;
import org.junit.jupiter.api.io.TempDir;
import org.mockito.ArgumentCaptor;
import java.net.http.*;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.io.ByteArrayOutputStream;
import java.util.List;
import java.util.concurrent.*;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;
import static io.github.bstronger1.workbench.Domain.*;

class ProviderSettingsTest {
    @TempDir Path temp;
    final ObjectMapper mapper = new ObjectMapper();
    final String alice = "a".repeat(64), bob = "b".repeat(64), key = "fake-test-key-12345678";
    ProjectStore store;
    ProviderSettings settings;
    @BeforeEach void setup() throws Exception {
        store = new ProjectStore(temp.toString(), mapper);
        settings = new ProviderSettings(store, mapper, "api.deepseek.com,api.openai.com");
    }
    ProviderSettings.Input input(boolean enabled, String secret) {
        return new ProviderSettings.Input(enabled, "https://api.deepseek.com/v1", "my-model", secret, 2.0, 8.0);
    }
    @Test void encryptedAtRestAndApiViewNeverIncludesKey() throws Exception {
        var view = settings.save(alice, input(true, key));
        assertEquals("••••••••5678", view.keyMask());
        assertFalse(mapper.writeValueAsString(view).contains(key));
        assertFalse(new String(Files.readAllBytes(temp.resolve("providers/" + alice + ".enc")), StandardCharsets.ISO_8859_1).contains(key));
        assertEquals(key, settings.active(alice).apiKey());
        assertFalse(input(true, key).toString().contains(key));
        assertFalse(settings.active(alice).toString().contains(key));
    }
    @Test void browserOwnersRemainIsolated() {
        settings.save(alice, input(true, key));
        assertFalse(settings.view(bob).hasKey()); assertNull(settings.active(bob));
        settings.clear(bob); assertNotNull(settings.active(alice));
    }
    @Test void blankPreservesKeyAndDisableThenClearWork() {
        settings.save(alice, input(true, key));
        settings.save(alice, input(false, ""));
        assertTrue(settings.view(alice).hasKey()); assertNull(settings.active(alice));
        settings.save(alice, input(true, "")); assertEquals(key, settings.active(alice).apiKey());
        settings.save(alice, input(true, "replacement-test-key")); assertEquals("replacement-test-key", settings.active(alice).apiKey());
        settings.clear(alice); assertFalse(settings.view(alice).hasKey()); assertNull(settings.active(alice));
    }
    @Test void settingsSurviveRestartWithTheSameMasterKey() throws Exception {
        settings.save(alice, input(true, key));
        var restarted = new ProviderSettings(store, mapper, "api.deepseek.com");
        assertEquals(key, restarted.active(alice).apiKey());
        assertEquals("my-model", restarted.view(alice).model());
    }
    @Test void copiedOrTamperedCiphertextCannotBeReadByAnotherOwner() throws Exception {
        settings.save(alice, input(true, key));
        Files.copy(temp.resolve("providers/" + alice + ".enc"), temp.resolve("providers/" + bob + ".enc"));
        assertThrows(IllegalStateException.class, () -> settings.active(bob));
        byte[] data = Files.readAllBytes(temp.resolve("providers/" + alice + ".enc"));
        data[data.length - 1] ^= 1;
        Files.write(temp.resolve("providers/" + alice + ".enc"), data);
        assertThrows(IllegalStateException.class, () -> settings.active(alice));
    }
    @Test void baseUrlRequiresExactAllowedHttpsHostAndSafePath() {
        assertEquals("https://api.deepseek.com/v1", settings.normalizeBaseUrl("https://api.deepseek.com/v1/chat/completions/"));
        for (String url : List.of("http://api.deepseek.com/v1", "https://127.0.0.1/v1", "https://api.deepseek.com.attacker.test/v1",
                "https://x:secret@api.deepseek.com/v1", "https://api.deepseek.com:8443/v1", "https://api.deepseek.com/v1?key=x",
                "https://api.deepseek.com/v1#x", "https://api.deepseek.com/../x"))
            assertThrows(IllegalArgumentException.class, () -> settings.normalizeBaseUrl(url), url);
        assertThrows(IllegalArgumentException.class, () -> settings.view("../escape"));
    }
    @Test void removedHostIsRevalidatedBeforeUse() throws Exception {
        settings.save(alice, input(true, key));
        var changed = new ProviderSettings(store, mapper, "api.openai.com");
        assertThrows(IllegalArgumentException.class, () -> changed.active(alice));
        changed.clear(alice); assertNull(changed.active(alice));
    }
    @Test void invalidInputCannotReplaceWorkingConfig() {
        assertThrows(IllegalArgumentException.class, () -> settings.save(alice, input(true, "")));
        settings.save(alice, input(true, key));
        assertThrows(IllegalArgumentException.class, () -> settings.save(alice, input(true, "abc\n123456")));
        assertThrows(IllegalArgumentException.class, () -> settings.save(alice,
                new ProviderSettings.Input(true,"https://api.deepseek.com","m",key,Double.NaN,0.0)));
        assertEquals(key, settings.active(alice).apiKey());
    }
    @Test void personalCredentialsDriveModelRequestAndUsage() throws Exception {
        GenerationModel model = spy(new GenerationModel(mapper, "server-secret", "https://api.openai.com/v1", "server-model"));
        HttpResponse<String> response = mock(HttpResponse.class);
        when(response.statusCode()).thenReturn(200);
        when(response.body()).thenReturn(mapper.writeValueAsString(java.util.Map.of("choices", List.of(java.util.Map.of("message", java.util.Map.of("content", "{\"html\":\"<h1>ok</h1>\"}"))), "usage", java.util.Map.of("prompt_tokens",10,"completion_tokens",20))));
        doReturn(response).when(model).send(any());
        settings.save(alice,input(true,key)); Run run = new Run(); run.mode="live";run.prompt="hello";
        var result = model.generate(run,null,List.of(),false,settings.active(alice));
        assertEquals("<h1>ok</h1>",result.html()); assertEquals(10,result.inputTokens());
        var request = ArgumentCaptor.forClass(HttpRequest.class); verify(model).send(request.capture());
        assertEquals("https://api.deepseek.com/v1/chat/completions",request.getValue().uri().toString());
        assertEquals("Bearer " + key, request.getValue().headers().firstValue("Authorization").orElseThrow());
        String body = requestBody(request.getValue());
        assertEquals("my-model",mapper.readTree(body).path("model").asText());
        assertFalse(body.contains(key)); assertFalse(body.contains("server-secret"));
    }
    @Test void connectionTestRequiresValidResponseAndNeverExposesProviderError() throws Exception {
        GenerationModel model = spy(new GenerationModel(mapper,"","https://api.openai.com/v1","unused"));
        HttpResponse<String> response = mock(HttpResponse.class); doReturn(response).when(model).send(any());
        settings.save(alice,input(true,key)); var credentials=settings.active(alice);
        when(response.statusCode()).thenReturn(401); when(response.body()).thenReturn(key);
        var error=assertThrows(IllegalStateException.class,()->model.testConnection(credentials)); assertFalse(error.getMessage().contains(key));
        when(response.statusCode()).thenReturn(200); when(response.body()).thenReturn("{\"choices\":[]}");
        assertThrows(IllegalStateException.class,()->model.testConnection(credentials));
        when(response.body()).thenReturn("{\"choices\":[{\"message\":{\"content\":\"OK\"}}]}");
        assertDoesNotThrow(()->model.testConnection(credentials));
    }
    @Test void workflowUsesPersonalModelAndNeverPersistsCredentials() throws Exception {
        GenerationModel model=mock(GenerationModel.class); ArtifactValidator validator=mock(ArtifactValidator.class);
        settings.save(alice,input(true,key)); var credentials=settings.active(alice);
        when(model.generate(any(),any(),anyList(),anyBoolean(),eq(credentials))).thenReturn(new ModelReply("html",100,200,true));
        when(validator.validate(anyString(),any(),anyInt())).thenReturn(new ArtifactValidator.Validation(List.of(),"PASSED",null));
        WorkflowEngine engine=new WorkflowEngine(store,new MemoryService(),model,validator,"demo",0,0);
        try {
            var project=store.create(alice,"app");
            var run=engine.submit(alice,project.id,new GenerateRequest("hello",0,24000,List.of(),true,"none",false),credentials);
            verify(model,timeout(5000)).generate(any(),isNull(),anyList(),eq(false),eq(credentials));
            long deadline=System.nanoTime()+TimeUnit.SECONDS.toNanos(5);
            Run completed;
            do { completed=store.get(alice,project.id).runs.getFirst(); if("PASSED".equals(completed.status)) break; Thread.sleep(10); } while(System.nanoTime()<deadline);
            assertEquals("PASSED",completed.status);assertEquals("live",completed.mode);assertEquals("my-model",completed.model);
            assertEquals(0.0018,completed.estimatedCost,0.0000001);
            assertFalse(Files.readString(temp.resolve(project.id+".json")).contains(key));
        } finally {engine.stop();}
    }
    private String requestBody(HttpRequest request) throws Exception {
        var bytes = new ByteArrayOutputStream(); var complete = new CompletableFuture<String>();
        request.bodyPublisher().orElseThrow().subscribe(new Flow.Subscriber<ByteBuffer>() {
            public void onSubscribe(Flow.Subscription subscription) {subscription.request(Long.MAX_VALUE);}
            public void onNext(ByteBuffer item) {byte[] data=new byte[item.remaining()];item.get(data);bytes.writeBytes(data);}
            public void onError(Throwable error) {complete.completeExceptionally(error);}
            public void onComplete() {complete.complete(bytes.toString(StandardCharsets.UTF_8));}
        });
        return complete.get(1,TimeUnit.SECONDS);
    }
}
