package io.github.bstronger1.workbench;

import com.fasterxml.jackson.databind.*;
import org.junit.jupiter.api.Test;
import java.util.*;
import static io.github.bstronger1.workbench.Domain.*;
import static org.junit.jupiter.api.Assertions.*;

class SkillWorkflowTest {
    @Test void apiForwardsSkillSettingAndPreservesTrace() {
        ObjectMapper mapper = new ObjectMapper();
        var ai = new AiClient(mapper, "http://127.0.0.1:18124", "x".repeat(40)) {
            @Override public JsonNode post(String path, Object body) {
                assertEquals(Boolean.FALSE, ((Map<?,?>)body).get("skillsEnabled"));
                return mapper.valueToTree(Map.of(
                    "status","PASSED","skillsEnabled",false,
                    "skillTrace",List.of(Map.of("attempt",0,"reason","disabled",
                        "references",List.of(),"contextChars",0,"contractHash","frozen"))
                ));
            }
        };
        Run run = new Run(); run.skillsEnabled=false; run.workflow="graph_single";
        run.prompt="make page";
        ai.execute("a".repeat(64), UUID.randomUUID().toString(), run,
            new ProviderSettings.Credentials("https://www.dmxapi.cn/v1","test","test-only-key",0,0),false);
        assertFalse(run.skillsEnabled);
        assertEquals("disabled",run.skillTrace.getFirst().reason());
        assertEquals("frozen",run.skillTrace.getFirst().contractHash());
        Run restored=mapper.convertValue(mapper.valueToTree(run),Run.class);
        assertEquals(run.skillTrace,restored.skillTrace);
    }

    @Test void legacyStoredRunsHaveNoSyntheticSkillHistory() throws Exception {
        Run restored=new ObjectMapper().readValue("{\"workflow\":\"graph_single\"}",Run.class);
        assertFalse(restored.skillsEnabled);
        assertTrue(restored.skillTrace.isEmpty());
    }
}
