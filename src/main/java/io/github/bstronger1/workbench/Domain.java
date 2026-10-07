package io.github.bstronger1.workbench;

import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;

public final class Domain {
    private Domain() {}
    public static String id() { return UUID.randomUUID().toString(); }
    public static String now() { return Instant.now().toString(); }
    public static class Project {
        public String id = id(), owner, name, createdAt = now();
        public List<Memory> memories = new ArrayList<>();
        public List<Document> documents = new ArrayList<>();
        public List<Run> runs = new ArrayList<>();
        public String selectedRunId;
    }
    public static class Memory {
        public String id = id(), key, value, kind, createdAt = now(), supersededBy;
        public boolean active = true;
    }
    public record Document(String id, String title, String content, String createdAt) {}
    public record Source(String id, String title, String excerpt, double score) {}
    public static class Run {
        public String id = id(), prompt, mode, model, memoryStrategy, status = "QUEUED", createdAt = now(), completedAt, error;
        public int maxRepairs, tokenBudget, inputTokens, outputTokens, calls;
        public String workflow = "legacy", contractHash;
        public boolean pauseAfterPlan, resumable;
        public List<Step> steps = new ArrayList<>();
        public java.util.Map<String,Object> plan = new java.util.LinkedHashMap<>();
        public boolean usageKnown = true;
        public long durationMs;
        public Double estimatedCost;
        public List<String> requiredTexts = new ArrayList<>();
        public boolean checkInteraction = true;
        public List<Source> memorySources = new ArrayList<>();
        public List<Event> events = new ArrayList<>();
        public List<Attempt> attempts = new ArrayList<>();
    }
    public record Event(String at, String stage, String message) {}
    public record Attempt(int number, String html, List<String> errors, String browserStatus, String screenshot, long durationMs) {}
    public record Step(String action, String target, String value) {}
    public record GenerateRequest(String prompt, Integer maxRepairs, Integer tokenBudget,
                                  List<String> requiredTexts, Boolean checkInteraction, String memoryStrategy, Boolean demoFailure, String workflow, List<Step> steps, Boolean pauseAfterPlan) {
        public GenerateRequest(String prompt, Integer maxRepairs, Integer tokenBudget, List<String> requiredTexts, Boolean checkInteraction, String memoryStrategy, Boolean demoFailure) {
            this(prompt,maxRepairs,tokenBudget,requiredTexts,checkInteraction,memoryStrategy,demoFailure,"legacy",List.of(),false);
        }
    }
    public record ModelReply(String html, int inputTokens, int outputTokens, boolean usageKnown) {}
}
