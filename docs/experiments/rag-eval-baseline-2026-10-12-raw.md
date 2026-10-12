# RAG Retrieval Evaluation

| reference_now | lookback_days | embedding_model | min_score |
| --- | --- | --- | --- |
| 2026-07-24T00:00:00+00:00 | 365 | bge-m3 | 0.500 |

## Questions

| id | symbol | question | positive | relevant_total | evidence_count | hit_at_k | precision_at_k | top1_relevant | max_score | relevant_max_score | relevant_min_score | irrelevant_max_score |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| nvda-china-export | NVDA | 중국 수출 규제가 엔비디아에 어떤 영향을 주고 있나? | 1.000 | 50 | 8 | 1.000 | 0.875 | 1.000 | 0.651 | 0.651 | 0.534 | 0.560 |
| nvda-next-gen-chips | NVDA | 블랙웰이나 루빈 같은 차세대 칩 출시 일정은? | 1.000 | 43 | 8 | 1.000 | 0.750 | 1.000 | 0.578 | 0.578 | 0.482 | 0.506 |
| nvda-quantum | NVDA | 엔비디아의 양자컴퓨팅 관련 행보는? | 1.000 | 4 | 8 | 1.000 | 0.125 | 0.000 | 0.552 | 0.518 | 0.518 | 0.552 |
| nvda-coreweave | NVDA | 엔비디아와 코어위브의 관계는? | 1.000 | 2 | 2 | 0.000 | 0.000 | 0.000 | 0.543 | 0.453 | 0.453 | 0.543 |
| nvda-earnings | NVDA | 엔비디아 최근 실적 발표 내용은? | 1.000 | 30 | 8 | 0.000 | 0.000 | 0.000 | 0.597 | 0.526 | 0.505 | 0.597 |
| googl-antitrust | GOOGL | 구글 반독점 소송은 어떻게 진행되고 있나? | 1.000 | 7 | 8 | 1.000 | 0.500 | 1.000 | 0.582 | 0.582 | 0.526 | 0.566 |
| googl-waymo | GOOGL | 웨이모 자율주행 사업 소식은? | 1.000 | 5 | 5 | 1.000 | 1.000 | 1.000 | 0.610 | 0.610 | 0.534 | 0.464 |
| googl-tpu | GOOGL | 구글 TPU 칩 관련 소식은? | 1.000 | 7 | 8 | 1.000 | 0.375 | 1.000 | 0.681 | 0.681 | 0.625 | 0.660 |
| googl-gemini | GOOGL | 제미나이 AI 모델의 경쟁력은? | 1.000 | 59 | 8 | 1.000 | 0.750 | 1.000 | 0.578 | 0.578 | 0.512 | 0.553 |
| aapl-broadcom | AAPL | 애플과 브로드컴의 칩 계약 내용은? | 1.000 | 41 | 8 | 1.000 | 1.000 | 1.000 | 0.776 | 0.776 | 0.661 | null |
| aapl-iphone | AAPL | 아이폰 판매 동향은? | 1.000 | 54 | 8 | 1.000 | 1.000 | 1.000 | 0.636 | 0.636 | 0.572 | 0.579 |
| aapl-app-store | AAPL | 앱스토어 반독점 규제 이슈는? | 1.000 | 35 | 5 | 1.000 | 0.800 | 1.000 | 0.554 | 0.554 | 0.463 | 0.507 |
| samsung-drop | 005930 | 삼성전자 주가 급락 배경은? | 1.000 | 21 | 8 | 1.000 | 1.000 | 1.000 | 0.942 | 0.942 | 0.590 | 0.686 |
| samsung-adr | 005930 | 삼성전자 ADR 상장 루머는? | 1.000 | 1 | 8 | 1.000 | 0.125 | 1.000 | 0.800 | 0.800 | 0.800 | 0.639 |
| neg-nvda-ceo | NVDA | 엔비디아 CEO 교체 계획은? | 0.000 | 0 | 8 | null | 0.000 | null | 0.549 | null | null | 0.549 |
| neg-aapl-vision-pro | AAPL | 애플 비전프로 판매 실적은? | 0.000 | 0 | 1 | null | 0.000 | null | 0.508 | null | null | 0.508 |
| neg-googl-ev | GOOGL | 구글의 전기차 사업 진출 계획은? | 0.000 | 0 | 8 | null | 0.000 | null | 0.627 | null | null | 0.627 |
| neg-samsung-buyback | 005930 | 삼성전자 자사주 소각 계획은? | 0.000 | 0 | 8 | null | 0.000 | null | 0.610 | null | null | 0.610 |

## Aggregate

| metric | value |
| --- | --- |
| positive_hit_at_k | 0.857 |
| positive_precision_at_k | 0.593 |
| positive_top1_rate | 0.786 |
| negative_zero_evidence_rate | 0.000 |
| negative_mean_evidence_count | 6.250 |
| negative_mean_max_score | 0.573 |
| relevant_score_median | 0.573 |
| relevant_score_max | 0.942 |
| irrelevant_score_median | 0.526 |
| irrelevant_score_max | 0.686 |

## Threshold Sweep

| threshold | positive_hit_at_k | positive_precision_at_k | negative_zero_evidence_rate |
| --- | --- | --- | --- |
| 0.300 | 0.857 | 0.571 | 0.000 |
| 0.350 | 0.857 | 0.571 | 0.000 |
| 0.400 | 0.857 | 0.571 | 0.000 |
| 0.450 | 0.857 | 0.571 | 0.000 |
| 0.500 | 0.857 | 0.593 | 0.000 |
| 0.550 | 0.786 | 0.667 | 0.500 |
| 0.600 | 0.500 | 0.792 | 0.500 |

## LLM Questions

| id | insufficient_evidence | answer_point_count | elapsed_seconds | error |
| --- | --- | --- | --- | --- |
| nvda-china-export | 0.000 | 4 | 106.208 | null |
| nvda-next-gen-chips | 0.000 | 3 | 5.448 | null |
| nvda-quantum | 1.000 | 2 | 6.154 | null |
| nvda-coreweave | 1.000 | 2 | 3.507 | null |
| nvda-earnings | 1.000 | 2 | 3.649 | null |
| googl-antitrust | 0.000 | 4 | 4.938 | null |
| googl-waymo | 0.000 | 3 | 4.327 | null |
| googl-tpu | 0.000 | 4 | 4.031 | null |
| googl-gemini | 0.000 | 5 | 7.186 | null |
| aapl-broadcom | 0.000 | 4 | 4.976 | null |
| aapl-iphone | 0.000 | 5 | 5.712 | null |
| aapl-app-store | 0.000 | 4 | 7.859 | null |
| samsung-drop | 1.000 | 2 | 4.265 | null |
| samsung-adr | 0.000 | 2 | 6.685 | null |
| neg-nvda-ceo | 1.000 | 2 | 4.170 | null |
| neg-aapl-vision-pro | 1.000 | 0 | 5.659 | null |
| neg-googl-ev | 1.000 | 1 | 3.148 | null |
| neg-samsung-buyback | 1.000 | 1 | 4.088 | null |

## LLM Aggregate

| metric | value |
| --- | --- |
| positive_insufficient_rate | 0.286 |
| negative_insufficient_rate | 1.000 |
| mean_elapsed_seconds | 10.667 |
| error_count | 0 |
