package mcfao.build;

import java.util.ArrayList;
import java.util.Collection;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;

import org.objectweb.asm.tree.ClassNode;

/** Small, deterministic runner for structural bytecode adaptation rules. */
final class AdaptationRuleEngine {
    static final int MAX_PASSES = 2;

    interface Rule {
        String id();
        String mechanism();
        String target(ClassNode node);
        boolean matches(ClassNode node);
        boolean alreadyApplied(ClassNode node);
        String preconditionFailure(ClassNode node);
        int apply(ClassNode node);
        String verificationFailure(ClassNode node);
    }

    private AdaptationRuleEngine() {}

    static List<Map<String, Object>> run(ClassNode node, Collection<? extends Rule> rules) {
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

            var byTarget = new HashMap<String, List<Rule>>();
            for (Rule rule : matched) {
                byTarget.computeIfAbsent(rule.target(node), ignored -> new ArrayList<>()).add(rule);
            }

            passes = pass;
            int changes = 0;
            for (Rule rule : matched) {
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
                changes += applied;
                outcomes.add(outcome(rule, target, pass, "APPLIED", applied,
                        "Bytecode postcondition verified"));
            }

            if (changes == 0) break;
            if (pass == MAX_PASSES) {
                var pending = rules.stream().filter(rule -> rule.matches(node))
                        .filter(rule -> !rule.alreadyApplied(node)).map(Rule::id).sorted().toList();
                if (!pending.isEmpty()) {
                    throw new IllegalStateException("MDAF did not converge after " + MAX_PASSES
                            + " passes; pending rules: " + pending);
                }
            }
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
        result.put("mechanism", rule.mechanism());
        result.put("target", target);
        result.put("pass", pass);
        result.put("status", status);
        result.put("changes", changes);
        result.put("validation", validation);
        return result;
    }
}
