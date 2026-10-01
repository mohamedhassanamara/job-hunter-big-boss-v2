# Credits

## job-hunter (jobhunt skills), MIT

Some ideas in this app are adapted from **job-hunter** by Mohamed Amine Hamdi,
<https://github.com/mohamedaminehamdi/job-hunter> (read at commit 6a96136). No code is imported or
vendored; the parts below were re-written for this app's data model. They are credited here, with
the license notice, as the MIT License asks.

| Here | Adapted from | What |
|---|---|---|
| `backend/app/services/fit_lexical.py` | `jobhunt-fit` | The lexical evidence check behind fit before/after: checkable terms per requirement line (your own skills as vocabulary, soft skills left out), evidence tagged by where it was found, evidenced / shown / dropped / unbacked, the years note |
| `backend/app/prompts/critique.md`, `backend/app/services/critique.py` | `jobhunt-critique` | The critique rubric and its order (unbacked claims, the opening, buried evidence, duties vs outcomes, specificity, real gaps); never open with praise, never suggest adding what the profile lacks, never rewrite |
| `backend/app/services/linkedin_track.py` | `jobhunt-outreach` | Code builds every LinkedIn link (the model never writes a URL); company-scoped people searches when the slug is known; alumni searched by school name; groups ordered by reply odds; length checked in code with one retry |
| `backend/app/services/linkedin.py` (sign-in wall check) | `jobhunt-posting` | A wall-phrase list plus a minimum length, then the paste fallback |

### License notice

```
MIT License

Copyright (c) 2026 Mohamed Amine Hamdi

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```
