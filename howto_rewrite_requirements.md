# How to rewrite requirements

- Agree the product scope and functional areas before editing requirements.
- Record the existing baseline. Preserve unrelated components and current work.
- Read the product specification, guides, implementation and tests. Record conflicts and missing behavior.
- Write a high-level description of the product purpose, users, functions and external interfaces.
- Write HLRs that state observable product responsibilities. Link each HLR to its product specification item.
- Derive LLRs with precise conditions, actions, limits and failure behavior. Give each LLR a parent HLR.
- Read the agreed writing standard, such as [ASD-STE100](https://www.asd-ste100.org/STE_faq.html). Use short sentences, active voice and consistent terms. Keep implementation detail out of HLRs.
- Assign unique IDs. Preserve a migration map for replaced, split or merged requirements; do not reuse retired IDs.
- Update implementation trace comments and reciprocal requirement references. Place each link beside the behavior it implements.
- Review test assertions before changing test links. Link LLTs to the LLRs they verify and HLTs to the HLRs they exercise.
- Update test plans and add missing checks. Distinguish partial verification, skipped tests and hardware checks from passed tests.
- Record or repair defects exposed by the tests. Do not weaken a requirement or assertion to hide a failure.
- Validate the hierarchy, references and trace links. Review changed parent links before clearing suspect status.
- Run the affected RBTs. Measure LLT coverage separately from HLT and ad-hoc execution.
- Publish the description, requirements, migration map and verification results. Report coverage gaps and unresolved inconsistencies.
- Check that unrelated components remain unchanged.
