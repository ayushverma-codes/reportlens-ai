# ReportLens AI
## Phase 7 — Final RAG Evaluation Report

**Project:** Multi-Document Conversational Report Intelligence  
**Evaluation Dataset:** 35 TCS annual-report questions  
**Generation Model:** GPT-OSS-20B (Groq)  
**Evaluation Judge:** Qwen3.8-27B (Groq)  
**Evaluation Framework:** RAGAS 0.4  
**Status:** Completed with documented evaluation limitations

---

### 1. Executive Summary

ReportLens AI was evaluated on 35 ground-truth questions covering factual retrieval, numerical analysis, financial comparisons, analytical reasoning, summarization and unanswerable queries.

All 35 questions were processed successfully. Following targeted improvements, the system achieved full reference-number coverage on applicable questions and correctly handled all five unanswerable questions.

Independent RAGAS judging was performed to assess factual correctness and faithfulness. The evaluation also identified areas requiring further improvement, particularly citation verification and complex analytical responses.

### 2. Final Evaluation Results

| Evaluation Metric | Result |
|---|---:|
| Automated tests | 83 passed |
| Questions processed | 35/35 |
| Expected-document retrieval coverage | 100% (30/30) |
| Factual-question numerical coverage | 100% |
| Numerical-question reference-number coverage | 100% |
| Comparison-question reference-number coverage | 100% |
| Unanswerable-question accuracy | 100% (5/5) |
| RAGAS factual correctness | 0.433 (27 scored) |
| RAGAS faithfulness | 0.880 (18 scored) |
| Generation failures in completed 35-question run | 0 |

**Metric interpretation:** Numerical coverage measures the presence of expected reference figures; it does not establish complete answer correctness. RAGAS averages exclude unscored cases.

### 3. Dataset Composition

| Question Category | Number |
|---|---:|
| Factual | 8 |
| Numerical | 5 |
| Comparison | 7 |
| Analysis | 8 |
| Summary | 2 |
| Unanswerable | 5 |
| **Total** | **35** |

### 4. RAGAS Assessment

**Factual Correctness**

All 30 answerable questions were submitted for factual-correctness evaluation. Twenty-seven produced valid numerical scores; three could not be scored because the judge's structured output exceeded its generation limit.

The observed average score was **0.433** across the 27 scored cases.

Several low scores occurred despite correct reference-number matches. These differences require careful interpretation because factual correctness assesses claim-level agreement, whereas reference-number coverage measures numerical matching.

**Faithfulness**

The faithfulness evaluation assessed whether generated statements were supported by retrieved context. Eighteen questions produced valid scores, with an observed average of **0.880**.

The remaining questions were not successfully scored due to judge capacity and quota restrictions. Faithfulness was evaluated using a reduced evidence window of two retrieved contexts, each limited to 1,800 characters.

### 5. Improvements Validated During Phase 7

The evaluation-driven corrections addressed:

- Constant-currency growth interpretation.
- Cross-year revenue calculations.
- Industry-segment financial comparisons.
- Calendar-year versus financial-year ambiguity.
- Citation-format recognition.
- Document-listing intent classification.
- Recognition of valid refusal language.
- Resume-safe evaluation and judge rate-limit handling.

Following these corrections, the numerical and comparison categories achieved full reference-number coverage in the saved evaluation results.

### 6. Limitations

The evaluation established strong document-level retrieval coverage and encouraging results for financial-number extraction. However, several limitations remain:

1. Retrieval coverage is measured at the expected-document level, not as verified page-level retrieval accuracy.
2. Numerical reference coverage does not measure completeness, contextual accuracy or unsupported claims.
3. RAGAS scores are based on the successfully scored subsets, not all 30 answerable questions.
4. Full claim-by-claim citation support verification remains outstanding.
5. Some RAGAS factual-correctness scores differ substantially from deterministic financial checks.
6. The evaluation uses four TCS annual reports; broader generalization across document types and organizations requires additional testing.

### 7. Conclusion

ReportLens AI successfully completed the 35-question evaluation run and demonstrated reliable retrieval of the expected source documents, improved numerical reference matching, and correct abstention behavior on the benchmark's five unanswerable questions.

The measured RAGAS faithfulness average of **0.880** on 18 scored cases indicates encouraging source-grounded generation within the restricted evidence window. The factual-correctness average of **0.433** on 27 scored cases shows that claim-level answer accuracy remains an important area for improvement and investigation.

**Phase 7 is concluded with documented findings and limitations.** The project can proceed to Phase 8, focusing on end-to-end reliability, session isolation, citation-support verification, performance and deployment readiness.