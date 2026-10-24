# Experiment results

## Overall (39 scenarios with at least one correct answer)

| system                   |   P@k |   R@k |   nDCG@k |   violation@k |   undisclosed_violations |   min_member_fit@k |   returned |   scenarios |
|:-------------------------|------:|------:|---------:|--------------:|-------------------------:|-------------------:|-----------:|------------:|
| chatbot:full             | 0.844 | 0.918 |    0.923 |         0.087 |                       13 |              0.862 |      4.718 |          39 |
| chatbot:no_clarification | 0.819 | 0.884 |    0.885 |         0.087 |                       13 |              0.831 |      4.718 |          39 |
| chatbot:no_fuzzy         | 0.812 | 0.876 |    0.889 |         0.097 |                       15 |              0.846 |      4.641 |          39 |
| chatbot:no_groupfit      | 0.844 | 0.918 |    0.923 |         0.087 |                       13 |              0.862 |      4.718 |          39 |
| chatbot:no_kg_multihop   | 0.844 | 0.918 |    0.918 |         0.087 |                       13 |              0.877 |      4.718 |          39 |
| chatbot:no_relaxation    | 0.844 | 0.918 |    0.923 |         0.067 |                       13 |              0.862 |      4.615 |          39 |
| chatbot:no_retrieval     | 0.839 | 0.912 |    0.92  |         0.087 |                       13 |              0.862 |      4.718 |          39 |
| keyword_search           | 0.219 | 0.228 |    0.249 |         0.563 |                       59 |              0.509 |      2.923 |          39 |
| llm_catalogue            | 0.243 | 0.247 |    0.272 |         0.627 |                      110 |              0.472 |      4.564 |          39 |
| llm_plain                | 0.032 | 0.034 |    0.054 |         0.562 |                       12 |              0.3   |      0.564 |          39 |
| site_filter              | 0.61  | 0.654 |    0.719 |         0.128 |                       23 |              0.985 |      4.308 |          39 |

## By tier

|                                                |   P@k |   R@k |   nDCG@k |   violation@k |   undisclosed_violations |   min_member_fit@k |   returned |   scenarios |
|:-----------------------------------------------|------:|------:|---------:|--------------:|-------------------------:|-------------------:|-----------:|------------:|
| ('chatbot:full', 'group')                      | 0.96  | 1     |    1     |         0     |                        0 |              0.829 |      5     |          10 |
| ('chatbot:full', 'itinerary')                  | 0.867 | 0.867 |    0.906 |         0     |                        0 |              1     |      2.8   |           5 |
| ('chatbot:full', 'multi')                      | 0.82  | 1     |    1     |         0.08  |                        0 |            nan     |      5     |          10 |
| ('chatbot:full', 'single')                     | 1     | 1     |    1     |         0     |                        0 |            nan     |      5     |           8 |
| ('chatbot:full', 'underspecified')             | 0.467 | 0.575 |    0.575 |         0.433 |                       13 |              0.85  |      5     |           6 |
| ('chatbot:no_clarification', 'group')          | 0.96  | 1     |    1     |         0     |                        0 |              0.829 |      5     |          10 |
| ('chatbot:no_clarification', 'itinerary')      | 0.867 | 0.867 |    0.906 |         0     |                        0 |              1     |      2.8   |           5 |
| ('chatbot:no_clarification', 'multi')          | 0.82  | 1     |    1     |         0.08  |                        0 |            nan     |      5     |          10 |
| ('chatbot:no_clarification', 'single')         | 1     | 1     |    1     |         0     |                        0 |            nan     |      5     |           8 |
| ('chatbot:no_clarification', 'underspecified') | 0.3   | 0.358 |    0.329 |         0.433 |                       13 |              0.75  |      5     |           6 |
| ('chatbot:no_fuzzy', 'group')                  | 0.96  | 1     |    1     |         0     |                        0 |              0.829 |      5     |          10 |
| ('chatbot:no_fuzzy', 'itinerary')              | 0.733 | 0.733 |    0.812 |         0     |                        0 |              1     |      2.2   |           5 |
| ('chatbot:no_fuzzy', 'multi')                  | 0.82  | 1     |    1     |         0.08  |                        0 |            nan     |      5     |          10 |
| ('chatbot:no_fuzzy', 'single')                 | 1     | 1     |    1     |         0     |                        0 |            nan     |      5     |           8 |
| ('chatbot:no_fuzzy', 'underspecified')         | 0.367 | 0.417 |    0.436 |         0.5   |                       15 |              0.8   |      5     |           6 |
| ('chatbot:no_groupfit', 'group')               | 0.96  | 1     |    1     |         0     |                        0 |              0.829 |      5     |          10 |
| ('chatbot:no_groupfit', 'itinerary')           | 0.867 | 0.867 |    0.906 |         0     |                        0 |              1     |      2.8   |           5 |
| ('chatbot:no_groupfit', 'multi')               | 0.82  | 1     |    1     |         0.08  |                        0 |            nan     |      5     |          10 |
| ('chatbot:no_groupfit', 'single')              | 1     | 1     |    1     |         0     |                        0 |            nan     |      5     |           8 |
| ('chatbot:no_groupfit', 'underspecified')      | 0.467 | 0.575 |    0.575 |         0.433 |                       13 |              0.85  |      5     |           6 |
| ('chatbot:no_kg_multihop', 'group')            | 0.96  | 1     |    0.989 |         0     |                        0 |              0.857 |      5     |          10 |
| ('chatbot:no_kg_multihop', 'itinerary')        | 0.867 | 0.867 |    0.906 |         0     |                        0 |              1     |      2.8   |           5 |
| ('chatbot:no_kg_multihop', 'multi')            | 0.82  | 1     |    0.995 |         0.08  |                        0 |            nan     |      5     |          10 |
| ('chatbot:no_kg_multihop', 'single')           | 1     | 1     |    1     |         0     |                        0 |            nan     |      5     |           8 |
| ('chatbot:no_kg_multihop', 'underspecified')   | 0.467 | 0.575 |    0.575 |         0.433 |                       13 |              0.85  |      5     |           6 |
| ('chatbot:no_relaxation', 'group')             | 0.96  | 1     |    1     |         0     |                        0 |              0.829 |      5     |          10 |
| ('chatbot:no_relaxation', 'itinerary')         | 0.867 | 0.867 |    0.906 |         0     |                        0 |              1     |      2.8   |           5 |
| ('chatbot:no_relaxation', 'multi')             | 0.82  | 1     |    1     |         0     |                        0 |            nan     |      4.6   |          10 |
| ('chatbot:no_relaxation', 'single')            | 1     | 1     |    1     |         0     |                        0 |            nan     |      5     |           8 |
| ('chatbot:no_relaxation', 'underspecified')    | 0.467 | 0.575 |    0.575 |         0.433 |                       13 |              0.85  |      5     |           6 |
| ('chatbot:no_retrieval', 'group')              | 0.96  | 1     |    1     |         0     |                        0 |              0.829 |      5     |          10 |
| ('chatbot:no_retrieval', 'itinerary')          | 0.867 | 0.867 |    0.906 |         0     |                        0 |              1     |      2.8   |           5 |
| ('chatbot:no_retrieval', 'multi')              | 0.82  | 1     |    1     |         0.08  |                        0 |            nan     |      5     |          10 |
| ('chatbot:no_retrieval', 'single')             | 0.975 | 0.975 |    0.989 |         0     |                        0 |            nan     |      5     |           8 |
| ('chatbot:no_retrieval', 'underspecified')     | 0.467 | 0.575 |    0.575 |         0.433 |                       13 |              0.85  |      5     |           6 |
| ('keyword_search', 'group')                    | 0.26  | 0.287 |    0.305 |         0.533 |                       17 |              0.419 |      3.3   |          10 |
| ('keyword_search', 'itinerary')                | 0.267 | 0.267 |    0.263 |         0.667 |                       10 |              0.333 |      3     |           5 |
| ('keyword_search', 'multi')                    | 0.22  | 0.22  |    0.278 |         0.659 |                       22 |            nan     |      3.6   |          10 |
| ('keyword_search', 'single')                   | 0.25  | 0.25  |    0.278 |         0.16  |                        4 |            nan     |      2.75  |           8 |
| ('keyword_search', 'underspecified')           | 0.067 | 0.083 |    0.058 |         0.867 |                        6 |              1     |      1.333 |           6 |
| ('llm_catalogue', 'group')                     | 0.4   | 0.413 |    0.447 |         0.46  |                       23 |              0.521 |      4.9   |          10 |
| ('llm_catalogue', 'itinerary')                 | 0.133 | 0.133 |    0.134 |         0.733 |                       11 |              0.167 |      3     |           5 |
| ('llm_catalogue', 'multi')                     | 0.16  | 0.165 |    0.176 |         0.77  |                       36 |            nan     |      4.7   |          10 |
| ('llm_catalogue', 'single')                    | 0.4   | 0.4   |    0.465 |         0.362 |                       14 |            nan     |      4.875 |           8 |
| ('llm_catalogue', 'underspecified')            | 0     | 0     |    0     |         0.933 |                       26 |              0.538 |      4.667 |           6 |
| ('llm_plain', 'group')                         | 0.02  | 0.02  |    0.034 |         0.5   |                        1 |              0.5   |      0.3   |          10 |
| ('llm_plain', 'itinerary')                     | 0.133 | 0.133 |    0.188 |         0.25  |                        1 |              0     |      0.8   |           5 |
| ('llm_plain', 'multi')                         | 0.04  | 0.045 |    0.072 |         0.6   |                        5 |            nan     |      0.9   |          10 |
| ('llm_plain', 'single')                        | 0     | 0     |    0.014 |         0.5   |                        1 |            nan     |      0.25  |           8 |
| ('llm_plain', 'underspecified')                | 0     | 0     |    0     |         1     |                        4 |              0.5   |      0.667 |           6 |
| ('site_filter', 'group')                       | 0.74  | 0.74  |    0.777 |         0.067 |                        3 |              0.971 |      4.3   |          10 |
| ('site_filter', 'itinerary')                   | 0.6   | 0.6   |    0.756 |         0.133 |                        2 |              1     |      3     |           5 |
| ('site_filter', 'multi')                       | 0.46  | 0.545 |    0.625 |         0.2   |                       10 |            nan     |      4.6   |          10 |
| ('site_filter', 'single')                      | 0.675 | 0.675 |    0.736 |         0.1   |                        4 |            nan     |      5     |           8 |
| ('site_filter', 'underspecified')              | 0.567 | 0.708 |    0.724 |         0.133 |                        4 |              1     |      4     |           6 |

## Impossible requests (no correct answer exists)

| system                   |   returned |   undisclosed_violations |
|:-------------------------|-----------:|-------------------------:|
| chatbot:full             |   1.66667  |                        0 |
| chatbot:no_clarification |   1.66667  |                        0 |
| chatbot:no_fuzzy         |   1.66667  |                        0 |
| chatbot:no_groupfit      |   1.66667  |                        0 |
| chatbot:no_kg_multihop   |   1.66667  |                        0 |
| chatbot:no_relaxation    |   1.66667  |                        0 |
| chatbot:no_retrieval     |   1.66667  |                        0 |
| keyword_search           |   1        |                        3 |
| llm_catalogue            |   4.66667  |                       14 |
| llm_plain                |   0.333333 |                        1 |
| site_filter              |   0        |                        0 |

## Interaction cost

Chatbot turns (mean): 1.52; questions asked in 15 of 42 scenarios

Site filter clicks (mean): 5.74; mean results left after filtering: 23.2

## LLM baselines

| system        |   hallucinated |   returned |   latency_s |
|:--------------|---------------:|-----------:|------------:|
| llm_catalogue |              4 |        210 |       59.52 |
| llm_plain     |            180 |        205 |       14.71 |

Consistency (mean Jaccard of top-5 across 3 runs): 
| system        |   jaccard |
|:--------------|----------:|
| llm_catalogue |     0.272 |
| llm_plain     |     0.411 |

## NLU

| mode   |   tp |   fp |   fn |   precision |   recall |    F1 |   latency_ms |
|:-------|-----:|-----:|-----:|------------:|---------:|------:|-------------:|
| hybrid |   99 |   78 |    4 |       0.559 |    0.961 | 0.707 |    49185.6   |
| llm    |   73 |  128 |   30 |       0.363 |    0.709 | 0.48  |    49574.3   |
| rules  |  100 |    2 |    3 |       0.98  |    0.971 | 0.976 |        5.667 |

## Planner

| solver     |   optimal_rate |   mean_gap |   worst_gap |   runtime_ms |   evaluations |
|:-----------|---------------:|-----------:|------------:|-------------:|--------------:|
| beam(w=1)  |         0      |     0.4026 |      0.654  |       0.1138 |       28.7143 |
| beam(w=4)  |         0.5357 |     0.0822 |      0.3111 |       0.4283 |      101.214  |
| beam(w=8)  |         0.75   |     0.0152 |      0.2169 |       0.8991 |      199.071  |
| exhaustive |         1      |     0      |      0      |      44.4837 |     9920      |
| genetic    |         0.9464 |     0.0077 |      0.2146 |      11.7535 |      316.886  |

## Grounded generation

| source   |   replies |
|:---------|----------:|
| llm      |        28 |
