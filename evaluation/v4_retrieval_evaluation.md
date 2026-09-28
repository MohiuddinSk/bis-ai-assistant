# V4 retrieval evaluation

Status: blocked before retrieval cases.

The validated candidate has 1,160 records, but normal production retrieval
filters on `default_retrieval=true`. The four Form V records have no such
metadata, and V4 additions are consequently excluded from ordinary retrieval.
The planned category, multilingual, regression, and candidate-response cases
would not be production-faithful and were not run.

Recommendation: do not promote; repair the additions metadata, create a new
candidate identity, then rerun the complete gate.
