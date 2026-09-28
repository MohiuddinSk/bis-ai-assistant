# Evaluator / production retrieval equivalence

`evaluation.evaluate_v4_retrieval.retrieve()` delegates directly to
`Retriever.search()`. The focused test compared ordered chunk IDs for English
and Bengali fee queries, battery toy, Form V, helmet, and a vague-product
query. All six matched exactly.
