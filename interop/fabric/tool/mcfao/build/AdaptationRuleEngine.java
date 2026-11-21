package mcfao.build;

import java.util.ArrayList;
import java.util.Collection;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import org.objectweb.asm.tree.ClassNode;

/** Small, deterministic runner for structural bytecode adaptation rules. */
final class AdaptationRuleEngine {
    static final int MAX_PASSES = 2;

    enum Mode { VERIFIED, EXPERIMENTAL, UNSUPPORTED }

    interface Rule {
        String id();
        int version();
        Mode mode();
        String mechanism();
        String scope();
        String evidence();
        String target(ClassNode node);
        boolean matches(ClassNode node);
        boolean alreadyApplied(ClassNode node);
        String preconditionFailure(ClassNode node);
        int apply(ClassNode node);
        String verificationFailure(ClassNode node);
    }

    private AdaptationRuleEngine() {}

    static List<Map<String, Object>> run(ClassNode node, Collection<? extends Rule> rules) {
        return run(node, rules, false);
    }

    static List<Map<String, Object>> run(ClassNode node, Collection<? extends Rule> rules,
            boolean allowExperimental) {
        var ids = new HashSet<String>();
        for (Rule rule : rules) {
            if (!ids.add(rule.id())) {
                throw new IllegalStateException("MDAF duplicate rule id: " + rule.id());
            }
        }

        var outcomes = new ArrayList<Map<String, Object>>();
        int passes = 0;
        for (int pass = 1; pass <= MAX_PASSES; pass++) {
            var matched = rules.stream().filter(rule -> rule.matches(node)).toList();
            if (matched.isEmpty()) {
                passes = Math.max(passes, pass - 1);
                break;
            }

            var enabled = new ArrayList<Rule>();
            var byTarget = new HashMap<String, List<Rule>>();
            for (Rule rule : matched) {
                if (rule.mode() == Mode.UNSUPPORTED || rule.mode() == Mode.EXPERIMENTAL && !allowExperimental) {
                    outcomes.add(outcome(rule, rule.target(node), pass, "SKIPPED_RULE_MODE", 0,
                            "Rule is not enabled in this build"));
                    continue;
                }
                enabled.add(rule);
                byTarget.computeIfAbsent(rule.target(node), ignored -> new ArrayList<>()).add(rule);
            }

            passes = pass;
            int changes = 0;
            for (Rule rule : enabled) {
                String target = rule.target(node);
                List<Rule> conflicts = byTarget.get(target);
                if (conflicts.size() > 1) {
                    String conflictingIds = conflicts.stream().map(Rule::id).sorted().toList().toString();
                    outcomes.add(outcome(rule, target, pass, "SKIPPED_RULE_CONFLICT", 0,
                            "Conflicting rules target the same bytecode: " + conflictingIds));
                    continue;
                }
                if (rule.alreadyApplied(node)) {
                    String failure = rule.verificationFailure(node);
                    if (failure != null) fail(rule, target, "idempotence check", failure);
                    outcomes.add(outcome(rule, target, pass, "VERIFIED_ALREADY_APPLIED", 0,
                            "Postcondition still holds; no edit repeated"));
                    continue;
                }

                String failure = rule.preconditionFailure(node);
                if (failure != null) {
                    outcomes.add(outcome(rule, target, pass, "SKIPPED_PRECONDITION", 0,
                            "Precondition not met: " + failure));
                    continue;
                }
                int applied = rule.apply(node);
                if (applied < 1) fail(rule, target, "apply", "rule reported no changes");
                failure = rule.verificationFailure(node);
                if (failure != null) fail(rule, target, "postcondition", failure);
                if (!rule.alreadyApplied(node)) fail(rule, target, "idempotence check", "edit could repeat");
                changes += applied;
                outcomes.add(outcome(rule, target, pass, "APPLIED", applied,
                        "Bytecode postcondition verified"));
            }

            if (changes == 0) break;

        }

        for (var outcome : outcomes) outcome.put("passes", passes);
        return List.copyOf(outcomes);
    }

    private static void fail(Rule rule, String target, String stage, String reason) {
        throw new IllegalStateException("MDAF rule " + rule.id() + " failed " + stage
                + " at " + target + ": " + reason);
    }

    private static Map<String, Object> outcome(Rule rule, String target, int pass,
            String status, int changes, String validation) {
        var result = new LinkedHashMap<String, Object>();
        result.put("id", rule.id());
        result.put("version", rule.version());
        result.put("mode", rule.mode().name());
        result.put("scope", rule.scope());
        result.put("evidence", rule.evidence());
        result.put("mechanism", rule.mechanism());
        result.put("target", target);
        result.put("pass", pass);
        result.put("status", status);
        result.put("changes", changes);
        result.put("validation", validation);
        return result;
    }
}
