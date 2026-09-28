# FMCS OCR audit

Offline local OCR only; no network, provider, or LLM calls.

## fmcs_application_form_v

- Pages: 2
- OCR characters per page: [944, 1133]
- Accepted/rejected lines: 43/8
- Chunks: 4
- Detected title: BUREAU OF INDIAN STANDARDS
- Pages needing manual review: []
- Representative accepted: ['Form - V', 'a (Refer clause (g) of sub-paragraph (1) of paragraph 3 of Scheme I)', 'BUREAU OF INDIAN STANDARDS']
- Representative rejected: [{'text': 'ee ee ee', 'reason': 'low_confidence'}, {'text': '1 1', 'reason': 'symbol_dominated_noise'}, {'text': '2 2', 'reason': 'symbol_dominated_noise'}]

## fmcs_application_checklist

- Pages: 4
- OCR characters per page: [2478, 2935, 2697, 568]
- Accepted/rejected lines: 157/56
- Chunks: 26
- Detected title: CHECK-LIST FOR APPLICATION TO BE SUBMITTED BY APPLICANT TO BIS
- Pages needing manual review: []
- Representative accepted: ['CHECK-LIST FOR APPLICATION TO BE SUBMITTED BY APPLICANT TO BIS', 'WHILE APPLYING FOR BIS LICENCE UNDER PRODUCT CERTIFICATION SCHEME OF BIS', 'The following check-list is required to be submitted with all the applications for grant of BIS licence under']
- Representative rejected: [{'text': '', 'reason': 'empty'}, {'text': 'No.', 'reason': 'symbol_dominated_noise'}, {'text': '1', 'reason': 'standalone_serial_number'}]
