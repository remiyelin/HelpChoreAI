# Structured Second Rater — muse-spark-1.3

Protocol replaces the deleted free-text keyword heuristic (it scored negations as affirmations). Author labels are never included in the prompt. `cannot_tell` is a separate category, never mapped to a label.

## Prompt (exact)

```
You are a second rater for research microscopy. You are shown frames of the same red blood cell in a microfluidic channel, each preceded by a short text id such as 'frame 1 of 3' and upscaled for visibility. Judge ONLY visible morphology. A spiculated cell has distinct pointed protrusions (spicules) on its outline. Set spiculated to yes if clear spicules are visible in any frame, no if the outline is smooth in all frames, and cannot_tell if the images do not allow a judgement. confidence is your probability that the spiculated judgement is correct. spicule_points lists the clearest spicule tips, each with its frame number and x and y on a 0-1000 grid with 0,0 at the top-left of that frame image. image_quality is poor if blur, darkness or artefacts prevent judgement. reason is at most 20 words, morphology only. Reply with the JSON object only.
```

## Enforced JSON schema

```json
{
 "type": "object",
 "additionalProperties": false,
 "properties": {
  "spiculated": {
   "type": "string",
   "enum": [
    "yes",
    "no",
    "cannot_tell"
   ]
  },
  "confidence": {
   "type": "number",
   "minimum": 0,
   "maximum": 1
  },
  "spicule_points": {
   "type": "array",
   "items": {
    "type": "object",
    "additionalProperties": false,
    "properties": {
     "frame": {
      "type": "integer"
     },
     "x": {
      "type": "integer",
      "minimum": 0,
      "maximum": 1000
     },
     "y": {
      "type": "integer",
      "minimum": 0,
      "maximum": 1000
     }
    },
    "required": [
     "frame",
     "x",
     "y"
    ]
   }
  },
  "image_quality": {
   "type": "string",
   "enum": [
    "ok",
    "poor"
   ]
  },
  "reason": {
   "type": "string"
  }
 },
 "required": [
  "spiculated",
  "confidence",
  "spicule_points",
  "image_quality",
  "reason"
 ]
}
```

Model: muse-spark-1.3, reasoning_effort=low, response_format json_schema (strict), up to 3 track frames per cell as separate image parts, each upscaled 4x nearest-neighbour. Sample: 80 queue cells (40 author health=1, 40 health=0 across P1/P2/P4, seed 42); 20 rated twice (repeat index in cache key).

## Results (first rating, n_ok=80/80)

Confusion vs author (rows author, cols rater; cannot_tell excluded): TP=8 FN=9 FP=6 TN=22.

Cohen kappa 0.266 (95% CI -0.028–0.545); Gwet AC1 0.392 (95% CI 0.098–0.664); PABAK 0.334; cannot_tell share 0.438.

Median spicule points by author health: {'0': 0.0, '1': 0.0}.

Intra-rater (20 repeats): {'n_pairs': 20, 'n_both_rated': 11, 'raw_agreement_3way': 0.75, 'kappa': 0.389, 'ac1': 0.741}.

## Example responses

```json
{
 "correct": {
  "spiculated": "no",
  "author_health": 0,
  "confidence": 0.65,
  "spicule_points": [],
  "image_quality": "ok",
  "reason": "Smooth outline without distinct pointed protrusions."
 },
 "wrong": {
  "spiculated": "yes",
  "author_health": 0,
  "confidence": 0.6,
  "spicule_points": [
   {
    "frame": 1,
    "x": 660,
    "y": 700
   }
  ],
  "image_quality": "ok",
  "reason": "Single sharp pointed tip at tapered end, otherwise smooth contour."
 },
 "cannot_tell": {
  "spiculated": "cannot_tell",
  "author_health": 0,
  "confidence": 0.4,
  "spicule_points": [],
  "image_quality": "poor",
  "reason": "Blurry dark cell with indistinct outline, possible point but unclear."
 }
}
```

Example crops with drawn spicule points: ['docs/media/rater_example_1.png (P2 cell 23: yes, author 1)', 'docs/media/rater_example_2.png (P2 cell 1: yes, author 1)', 'docs/media/rater_example_3.png (P1 cell 42: yes, author 1)', 'docs/media/rater_example_4.png (P1 cell 20: yes, author 1)', 'docs/media/rater_example_5.png (P1 cell 91: no, author 0)', 'docs/media/rater_example_6.png (P1 cell 24: cannot_tell, author 0)']. Detail: data/tables/rater_spark.csv. New API calls this run: 100 (all cached; reruns free).

## Open-weight second rater — muse-spark-open via Baseten (P-09)

Exact same protocol as above: same 80 stratified cells (40 author health=1, 40 health=0 across
P1/P2/P4, seed 42), same upscaled 4x track frames, exact `RATER_PROMPT` and `RATER_SCHEMA`.
The model is called directly as `meta-models/muse-spark-open` on Baseten; only
`message.content` is parsed (`reasoning_content` ignored), the JSON is validated in Python
against the schema, with one retry on invalid JSON before falling back to null.
No retry was needed. Author labels are never sent. Detail: data/tables/rater_open.csv
(`src/rater_open.py`, `meta_api.baseten_rater`). New API calls: 80 first calls, 0 retries
(all cached; reruns free).

Results (first rating, n_ok=80/80): confusion vs author (cannot_tell excluded):
TP=16 FN=10 FP=6 TN=26. Cohen kappa 0.434 (95% CI 0.201–0.663); Gwet AC1 0.464
(95% CI 0.245–0.694); PABAK 0.448; cannot_tell share 0.275.
For comparison, cloud muse-spark-1.3 (P-05) on the same cells: kappa 0.266, AC1 0.392,
PABAK 0.334, cannot_tell share 0.438.

Head-to-head, cloud muse-spark-1.3 vs open-weight muse-spark-open (same 80 cells):
80 pairs, 38 both rated yes/no; 3-way raw agreement 0.600; on the both-rated subset
kappa 0.689, AC1 0.772, PABAK 0.736.
