package io.github.bstronger1.workbench;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.test.util.ReflectionTestUtils;
import java.nio.file.Path;
import java.util.*;
import static io.github.bstronger1.workbench.Domain.*;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;
class AiWorkflowTest {
 @TempDir Path temp;
 @Test void graphRunsUseQueueAndResumeWithinOwnedProject() throws Exception {
  var store=new ProjectStore(temp.toString(),new ObjectMapper());var ai=mock(AiClient.class);when(ai.enabled()).thenReturn(true);
  var engine=new WorkflowEngine(store,new MemoryService(),mock(GenerationModel.class),mock(ArtifactValidator.class),"demo",0,0);
  ReflectionTestUtils.setField(engine,"ai",ai);
  var credentials=new ProviderSettings.Credentials("https://www.dmxapi.cn/v1","test","test-only-key",0,0);
  doAnswer(invocation->{Run r=invocation.getArgument(2);boolean resume=invocation.getArgument(4);r.status=resume?"PASSED":"AWAITING_APPROVAL";r.resumable=!resume;r.calls=resume?3:1;return null;}).when(ai).execute(anyString(),anyString(),any(),any(),anyBoolean());
  try {
   var p=store.create("alice","graph");
   var r=engine.submit("alice",p.id,new GenerateRequest("make app",1,50000,List.of("test"),true,"none",false,"graph_multi",List.of(new Step("click","primary-action",""),new Step("assert_changed","result","")),true),credentials);
   await(store,p.id,r.id,"AWAITING_APPROVAL");
   assertThrows(NoSuchElementException.class,()->engine.resume("bob",p.id,r.id,credentials));
   engine.resume("alice",p.id,r.id,credentials);await(store,p.id,r.id,"PASSED");
   assertEquals(3,Api.findRun(store.get("alice",p.id),r.id).calls);
   verify(ai).execute(eq("alice"),eq(p.id),any(),eq(credentials),eq(false));
   verify(ai).execute(eq("alice"),eq(p.id),any(),eq(credentials),eq(true));
  } finally {engine.stop();}
 }
 private void await(ProjectStore s,String p,String r,String status) throws Exception {
  long until=System.currentTimeMillis()+3000;
  while(System.currentTimeMillis()<until) {if(Api.findRun(s.get("alice",p),r).status.equals(status))return;Thread.sleep(20);}
  fail("Expected status "+status);
 }
 @Test void contractsRejectSelectorsAndMissingAssertions() {
  assertThrows(IllegalArgumentException.class,()->WorkflowEngine.validateSteps(List.of(new Step("click","x] script",""))));
  assertThrows(IllegalArgumentException.class,()->WorkflowEngine.validateSteps(List.of(new Step("click","primary-action",""))));
  assertThrows(IllegalArgumentException.class,()->WorkflowEngine.validateSteps(List.of(new Step("click","primary-action",""),new Step("assert_text","result",""))));
 }
 @Test void runningGraphKeepsResumeCapabilityAcrossJavaRestart() throws Exception {
  var store=new ProjectStore(temp.toString(),new ObjectMapper());var p=store.create("alice","restore");
  Run r=new Run();r.workflow="graph_multi";r.resumable=true;r.status="RUNNING";
  store.update("alice",p.id,x->{x.runs.add(r);return null;});
  var reloaded=new ProjectStore(temp.toString(),new ObjectMapper());
  var restored=Api.findRun(reloaded.get("alice",p.id),r.id);
  assertEquals("INTERRUPTED",restored.status);assertTrue(restored.resumable);
 }
 @Test void sidecarAddressCannotTargetExternalOrUnauthenticatedService() {
  assertThrows(IllegalArgumentException.class,()->new AiClient(new ObjectMapper(),"http://example.com:18124","x".repeat(40)));
  assertThrows(IllegalArgumentException.class,()->new AiClient(new ObjectMapper(),"http://127.0.0.1:18124","short"));
 }
}