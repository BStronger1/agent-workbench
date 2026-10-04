package io.github.bstronger1.workbench;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.*;
import org.junit.jupiter.api.io.TempDir;
import java.nio.file.Path;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;
import static io.github.bstronger1.workbench.Domain.*;
import static org.mockito.Mockito.*;

class CoreTest {
    @TempDir Path temp;
    ProjectStore store;
    MemoryService memory = new MemoryService();
    @BeforeEach void setup() throws Exception { store = new ProjectStore(temp.toString(), new ObjectMapper()); }
    @Test void projectIsolation() {
        Project p = store.create("alice", "A");
        assertThrows(NoSuchElementException.class, () -> store.get("bob", p.id));
        assertTrue(store.list("bob").isEmpty());
    }
    @Test void snapshotCannotMutateStore() {
        Project p = store.create("alice", "A"); p.name = "tamper";
        assertEquals("A", store.get("alice",p.id).name);
    }
    @Test void dataSurvivesRestartAndInterruptedRunsAreHonest() throws Exception {
        Project p = store.create("alice", "A"); Run r = new Run(); r.status="RUNNING";
        store.update("alice",p.id,x->{x.runs.add(r);return null;});
        ProjectStore reload = new ProjectStore(temp.toString(), new ObjectMapper());
        assertEquals("INTERRUPTED", reload.get("alice",p.id).runs.getFirst().status);
    }
    @Test void failedUpdateDoesNotChangeProject() {
        Project p=store.create("a","safe");
        assertThrows(IllegalArgumentException.class,()->store.update("a",p.id,x->{x.name="bad";throw new IllegalArgumentException();}));
        assertEquals("safe",store.get("a",p.id).name);
    }
    @Test void updatesSupersedeMemoryAndForgetRemovesItFromRetrieval() {
        Project p=new Project(); Memory first=memory.remember(p,"constraint","颜色","蓝色");
        Memory second=memory.remember(p,"constraint","颜色","绿色");
        assertFalse(first.active); assertEquals(second.id,first.supersededBy);
        var results=memory.retrieve(p,"颜色",false); assertEquals(1,results.size()); assertEquals("绿色",results.getFirst().excerpt());
        second.active=false; assertTrue(memory.retrieve(p,"颜色",false).isEmpty());
    }
    @Test void chineseRetrievalIncludesParagraphSourceAndNoMatchAbstains() {
        Project p=new Project(); p.documents.add(new Document("doc-1","计划","目标用户为研究生。预算为三百元。",now()));
        var sources=memory.retrieve(p,"目标用户",true); assertEquals("doc-1:0",sources.getFirst().id());
        assertTrue(memory.retrieve(p,"xyz789",true).isEmpty());
    }
    @Test void memoryAblationsHaveSeparateInputs() {
        Project p=new Project(); memory.remember(p,"constraint","颜色","绿色"); Run r=new Run();r.prompt="旧需求";p.runs.add(r);
        assertTrue(memory.context(p,"颜色","none").isEmpty());
        assertEquals("旧需求",memory.context(p,"颜色","window").getFirst().excerpt());
        assertEquals("绿色",memory.context(p,"颜色","retrieval").getFirst().excerpt());
    }
    @Test void validatorRejectsExternalAndMissingRequirements() {
        var errors=ArtifactValidator.staticErrors("<h1>hello</h1><script src='https://x.com/a.js'></script>",List.of("需求"),true);
        assertTrue(errors.stream().anyMatch(s->s.contains("外部")));
        assertTrue(errors.stream().anyMatch(s->s.contains("验收文本")));
        assertTrue(errors.stream().anyMatch(s->s.contains("交互")));
    }
    @Test void demoEscapesUserInputAndPassesStaticChecks() throws Exception {
        GenerationModel model=new GenerationModel(new ObjectMapper(),"","https://example.com","demo");
        Run r=new Run();r.mode="demo";r.prompt="<script>alert(1)</script>";r.requiredTexts=List.of("任务");
        String html=model.generate(r,null,List.of(),false).html();
        assertFalse(html.contains("<script>alert(1)</script>"));
        assertTrue(ArtifactValidator.staticErrors(html,r.requiredTexts,true).isEmpty());
    }
    @Test void boundedRepairUsesFailuresAndSelectsOnlySuccessfulVersion() throws Exception {
        GenerationModel model=mock(GenerationModel.class); ArtifactValidator validator=mock(ArtifactValidator.class);
        when(model.generate(any(),any(),anyList(),anyBoolean())).thenReturn(new ModelReply("v1",0,0,true),new ModelReply("v2",0,0,true));
        when(validator.validate(anyString(),any(),anyInt())).thenReturn(new ArtifactValidator.Validation(List.of("button broken"),"FAILED",null),new ArtifactValidator.Validation(List.of(),"PASSED",null));
        WorkflowEngine engine=new WorkflowEngine(store,memory,model,validator,"demo",0,0);
        try { Project p=store.create("a","app"); Run r=new Run();r.prompt="x";r.mode="demo";r.maxRepairs=1;store.update("a",p.id,x->{x.runs.add(r);return null;});
            engine.execute("a",p.id,r,false);
            assertEquals("PASSED",r.status); assertEquals(2,r.attempts.size()); assertEquals(r.id,store.get("a",p.id).selectedRunId);
            verify(model).generate(r,"v1",List.of("button broken"),false);
        } finally {engine.stop();}
    }
    @Test void brokenInfrastructureIsNotPassedOrRetried() throws Exception {
        GenerationModel model=mock(GenerationModel.class); ArtifactValidator validator=mock(ArtifactValidator.class);
        when(model.generate(any(),any(),anyList(),anyBoolean())).thenReturn(new ModelReply("v1",0,0,true));
        when(validator.validate(anyString(),any(),anyInt())).thenReturn(new ArtifactValidator.Validation(List.of("worker down"),"ERROR",null));
        WorkflowEngine engine=new WorkflowEngine(store,memory,model,validator,"demo",0,0);
        try { Project p=store.create("a","app"); Run r=new Run();r.prompt="x";r.mode="demo";r.maxRepairs=3;engine.execute("a",p.id,r,false);
            assertEquals("FAILED",r.status);assertNull(store.get("a",p.id).selectedRunId);assertEquals(1,r.attempts.size());
        } finally {engine.stop();}
    }
    @Test void repairBudgetStopsCalls() throws Exception {
        GenerationModel model=mock(GenerationModel.class); ArtifactValidator validator=mock(ArtifactValidator.class);
        WorkflowEngine engine=new WorkflowEngine(store,memory,model,validator,"live",0,0);
        try {Project p=store.create("a","app");Run r=new Run();r.prompt="x";r.mode="live";r.tokenBudget=1000;engine.execute("a",p.id,r,false);
            assertEquals("BUDGET_EXCEEDED",r.status);verifyNoInteractions(model);
        } finally {engine.stop();}
    }
    @Test void noBrowserCannotBeReportedAsFullPass() throws Exception {
        GenerationModel model=mock(GenerationModel.class); ArtifactValidator validator=mock(ArtifactValidator.class);
        when(model.generate(any(),any(),anyList(),anyBoolean())).thenReturn(new ModelReply("v1",0,0,true));
        when(validator.validate(anyString(),any(),anyInt())).thenReturn(new ArtifactValidator.Validation(List.of(),"NOT_CONFIGURED",null));
        WorkflowEngine engine=new WorkflowEngine(store,memory,model,validator,"demo",0,0);
        try { Project p=store.create("a","app"); Run r=new Run();r.prompt="x";r.mode="demo";engine.execute("a",p.id,r,false);assertEquals("STATIC_VALIDATED",r.status); }
        finally {engine.stop();}
    }
}
