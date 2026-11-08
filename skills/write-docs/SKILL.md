---
name: write-docs
description: Draft, rewrite, edit, or restructure documents, reports, proposals, memos, and other written deliverables for a user to read or share. Use when the work requires judgment about content, structure, or clarity, regardless of output format. Excludes routine code comments and commit messages.
---

# Write Documents

Give the intended reader enough information in the document itself to understand the topic, make a judgment, or complete a task. Use format-specific skills for file creation, layout, and technical validation. Use this skill to decide how to develop the content so the reader can follow it.

Apply this skill when drafting, rewriting, editing, or reorganizing a document in any format, including chat, artifacts, Word, and Markdown. Skip it for copying, extraction, calculation, format conversion, or code generation that requires no substantive editorial judgment. System, developer, and user instructions take precedence.

Scale the planning and review below to the task. Use the steps as a writing process and choose the delivered document's sections according to its purpose. Handle short pieces without extra forms. Keep working notes and review records out of the document unless the user requests them.

## 1. Determine how the reader will use the document

Before writing, identify what readers already know and what they should be able to explain, decide, look up, or do after reading. Establish their starting point from the user's background information and the context already established. When their background is unclear, start where a general reader can follow. Treat information you learned while researching as new to the reader unless the context establishes otherwise.

| Reader's purpose | How to organize the content |
|---|---|
| Learn or understand how something works | Begin with a familiar situation and an unresolved problem, then develop the solution and the concepts needed to understand it. |
| Decide, evaluate, or approve | State what needs to be decided and give enough of the conclusion to orient the reader, then provide the criteria, evidence, options, and tradeoffs. |
| Carry out a procedure | Follow the order in which the reader will act. Give prerequisites, the object of each action, expected results, and completion criteria where needed. |
| Look up information | Organize by the names or questions readers will search for. Give each lookup entry the definitions and conditions needed to use it. |

A document can serve several purposes. Separate the main explanation from reference material. A beginner's explanation should build understanding even when the source material is already organized as a glossary. A lookup table can stay compact.

## 2. Outline in the order the reader needs to understand things

Identify what the reader needs to learn between their starting point and their goal. Use those dependencies to order paragraphs and sections. The organization of the sources, the layout of the code, and the order in which you discovered information can help you check coverage. Build the outline around the order in which the reader needs the information.

For an explanation, use plain language to connect the situation the reader knows, the problem still to solve, the approach taken, and the result. At each transition, identify what the previous part established and what question follows from it. If an outline lists only terms, modules, or formulas, spell out their purposes and how they relate before choosing headings.

When introducing an important person, object, or component, make its role in the overall work clear. By the time readers encounter a new concept, they should know the current problem and why the concept helps. A definition gives the meaning of a term. Use the surrounding explanation to show why the reader needs it at that point.

When explaining a process, track where the object or data came from, its current state, what changes it, and who uses the result. When switching examples or moving to a different level of processing, connect the new entities to the objects and purpose already established. When introducing a person, tool, module, or function, explain what work it takes on in the process.

Establish the cause-and-effect relationships needed for the main task before introducing optimizations, special branches, and exceptions. When inserting a detail, explain how it changes the object being handled, the approach, or the result. Reconnect the explanation to the open question afterward. Move details that serve no such purpose to a reference section or omit them. Introduce constraints early enough to qualify any part of the main explanation they affect. Give content prominence in proportion to its importance.

Use headings and the immediately preceding text to make each section's subject and question identifiable before the reader reaches the body. When shortening a name or dropping a qualifier, retain enough wording to identify what it belongs to and how it relates. Rewrite headings that have another plausible reading. Use tables to compare things the reader can already identify, and use explanation to establish their relationships. Choose a format that serves the reader's purpose. Give each section the opening, questions, or summary it actually needs.

## 3. Make actors, actions, and results clear

When describing an operation or procedure, track who acts, under what conditions or at what stage, what they act on, what they do, and what results. Make those relationships clear in the sentence or the surrounding text. Omit subjects, objects, or timing when readers can infer them unambiguously, without mechanically repeating every detail in every sentence.

Distinguish stages such as computing a result, storing data, taking an action, and displaying an effect. Restore the specific name or relationship whenever an abbreviation, pronoun, or omitted object could refer to more than one actor, item, or stage. Help readers connect any later label to the original referent. Use transitions such as “therefore” and “next” only when the text establishes the cause, condition, or sequence they express.

Use familiar, precise language. Prefer ordinary words when they convey the intended meaning. Split sentences along lines of meaning when multiple actions, conditions, or shifts make them hard to follow.

Introduce terms and formulas once the problem they address is clear. Explain their function in terms the reader already understands, then give the name or precise notation. Ground any jargon, abstract classification, or contrast in a concrete explanation of the concept itself. Define necessary terms and abbreviations at first use and use their names consistently afterward.

Before introducing a formula, code, or another implementation detail, establish which problem it addresses, what known information it uses, and what work the result supports. Then explain the mechanism to the depth the reader needs. A call chain or handoff sequence establishes execution order. Readers learning how the system works also need to know what each part actually does and why. For readers looking up where a familiar operation is implemented, give the name and source directly.

Use examples to demonstrate relationships that are difficult to grasp from the explanation alone. Reuse the established situation where possible so readers can see concrete inputs, changes, and results. State simplifying assumptions that affect the conclusion so readers can tell which values or conditions apply only to the example. If the example requires unfamiliar background, simplify it or supply the prerequisites first.

## 4. Choose content and precision based on what the reader needs

Use the smallest amount of information that still meets the reading goal. Cut repetition, vague statements, tangents, and detail included solely for completeness. Before removing a sentence, check whether the reader can still tell why the next step is needed, who is handling what, and how the conclusion follows. A sentence that connects two steps in the reasoning can matter even if it introduces no new terms.

Keep assumptions and limitations that change how readers understand, decide, act, or maintain something. Move secondary exceptions, audit evidence, and full sources to suitable supplementary material when helpful. Keep the main text understandable on its own. Use source links to support claims and let readers investigate further, with the essential explanation in the text.

Distinguish facts, evidence, interpretations, assumptions, estimates, and recommendations. Explain significant uncertainty where it affects a judgment. Label conjectures and preferences as such. When presenting options, explain the relevant conditions, benefits, limitations, and costs that inform the choice.

Write for readers who see only the delivered document. Choose content based on the subject and the reader's purpose. Include the user's requests, research history, earlier drafts, or rejected options only when the user explicitly asks for a relevant history or decision record. Cut newly written sentences too when their only purpose is to answer an editing discussion. For example, after removing a scoring system, present the criteria that still apply and omit commentary about the removal.

## 5. Rebuild the affected reading sequence when revising

Understand the existing document's purpose, audience, main thread, and terminology first. Determine whether feedback reveals a missing premise, a sequencing problem, an ambiguous reference, a detail introduced too early, or a factual error. Revise the structure that carries the problem. Reorder, merge, move, or delete material when that addresses the cause.

Use specific feedback as evidence of a possible broader problem. Find where readers lose the premise they need and fix the relevant passages. Add a general rule or a new section only if the underlying issue and the reader's needs warrant it. After revising, use the review in section 6 to reconstruct the affected reading sequence. When a change affects several sections, trace the related concepts through the whole document.

Remove reminders, comparisons, and defenses that made sense only in the earlier draft. Give recent feedback the space it merits for the reader's purpose. Keep scope, tone, terminology, and level of detail consistent throughout.

## 6. Reconstruct the reader's understanding in order, then verify the facts

Begin the review with the reader's background from section 1 and read the document in order. Check whether the opening establishes the document's purpose. At each point, reconstruct what the reader can understand using only the material encountered so far and the stated background. Judge earlier passages before relying on explanations that appear later.

For a continuous explanation, apply the following steps in the order the reader encounters the material. Include headings and paragraphs, and read figures, tables, examples, and code alongside the text that introduces them. Check whether each heading identifies its subject and question when it first appears.

1. **Restate what the reader now understands.** In a sentence or two, describe the problem, the objects involved, how an action changes them, and what the result is used for. A restatement of names, calls, or step order alone does not demonstrate understanding of how the process works. Keep only what affects later understanding. Distinguish the stated premises, the author's example choices, and the actual results.
2. **Check the next part's prerequisites and references.** Identify the objects, relationships, and process state it expects the reader to know. Compare them with the restatement. Check what each name, omission, and modifier refers to. If another reading is plausible, revise the wording to resolve it. Introduce new information where needed. If the text treats something as already known or completed, verify that the preceding material establishes it. Fix the earliest gap using the document itself.
3. **Check how the new material advances understanding.** Confirm that the information connects to the current question and that the action or reasoning supports the stated result. Update what the reader now knows. When switching to an implementation, example, or branch, make sure the original problem stays traceable. On returning to the main thread, explain what the inserted material contributed. If the sequence establishes only that another event happened next, clarify the relationship before continuing.

Check that the evidence establishes the relationships the reader needs. The appearance of a name, symbol, or value confirms only that it was mentioned. Check whether the document establishes what it represents, where it came from, or why it is being handled. Figures, tables, and code can supply this information without duplicating it in prose, as long as readers can tell how they relate to the explanation. Apply the same standard to actions and inferences. If a passage assumes that earlier work was completed or a conclusion was reached, find the corresponding process or reasoning in the preceding text.

For a short piece, restate the reader's understanding directly. For a long document, keep brief working notes on what has been established and which questions remain open, so the review does not silently fill gaps. Keep those notes separate from the text and the deliverables. For reference material, start from each independent entry's stated prerequisites and review it as a unit readers can use on its own.

At section boundaries, check that the previous result supports the problem taken up next. At the end, use only the document to restate the full process, compare the options, or walk through the procedure, as appropriate to the original reading goal. After a revision, restart before the gap and continue through the affected passages to catch repetition, contradictions, and broken references.

Separately verify facts, inferences, numbers, sources, code, links, and layout. Judge technical checks and checks of reader understanding independently. Repeated rereading does not replace either kind of check. The author's reconstruction is a limited check. A first-time reader's walkthrough provides direct evidence of what a new reader understands. When that feedback is available, revise based on what readers could explain in their own words and where they got stuck. At delivery, report only the checks actually completed and the scope they covered.
