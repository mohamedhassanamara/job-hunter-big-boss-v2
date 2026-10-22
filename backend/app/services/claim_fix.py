"""Suggested fixes for the claims the verifier flags (no model call of their own).

Every blocking claim gets one `fix` stored in the verification record:
- code first (`deterministic`): a years claim becomes the approved wording, a wrong number or tool
  becomes the one in the claim's source quote, a banned phrase is removed, a greeting gets the
  contact's name;
- else Claude's `suggestion` from the SAME verification call, if its quote is really in the source
  it names;
- every candidate goes through the code checks (numbers, tools, years, honesty, banned phrases):
  one that fails is replaced by "remove this sentence".
A fix never changes what blocks approval: it only edits text you then re-verify (`apply`).
"""

import re
from dataclasses import dataclass
from typing import Any

from sqlmodel import Session

from app.models import Application
from app.services import honesty
from app.services import verifier as vf
from app.services.cv_check import new_tools, numbers
from app.services.cv_claims import Vocabulary, years_claims

REMOVE = "remove"
REPLACE = "replace"


class FixError(Exception):
    """Shown to the user: the fix can't be applied (the text changed, or that part is fixed)."""


def _fix(kind: str, text: str = "", *, origin: str, note: str, source_id: str = "",
         source_quote: str = "") -> dict[str, str]:
    return {"kind": kind, "text": text, "origin": origin, "note": note, "source_id": source_id,
            "source_quote": source_quote}


@dataclass
class Fixer:
    """What the checks need to judge a candidate sentence: the sources and the letter context
    (allowed years, exact wording, banned phrases, honesty rules, language, contact name)."""

    sources: dict[str, str]
    ctx: Any = None

    # ---------------------------------------------------------------- the code checks
    def problems(self, sentence: str) -> list[str]:
        """Why a candidate sentence may not be shown as a fix (empty = it passes)."""
        from app.services import letter_check as lc

        out: list[str] = []
        known = {n.lower() for n in numbers(" ".join(self.sources.values()))}
        digits = {re.sub(r"\D", "", n) for n in known}
        for n in numbers(sentence):
            if n.lower() not in known and re.sub(r"\D", "", n) not in digits:
                out.append(f"“{n}” isn't in the sources")
        vocabulary = Vocabulary(" ".join(self.sources.values()))
        out += [f"“{t}” isn't in the sources" for t in new_tools(sentence, vocabulary)]
        if self.ctx is not None:
            out += [f"years claim “{c}”" for c in lc.years_problems(sentence, self.ctx)]
            out += [m for _k, _s, m in honesty.problems(sentence, self.ctx.honesty)]
            out += [v["message"] for v in lc._banned(sentence, self.ctx)]
        return out

    # ------------------------------------------------------------------- code fixes
    def deterministic(self, row: dict[str, Any]) -> tuple[str, str] | None:
        """(new sentence, what changed) for an error code can repair, else None."""
        sentence: str = row["sentence"]
        quote: str = row.get("source_quote") or ""
        ctx = self.ctx
        if ctx is not None:
            if hit := self._banned(sentence):
                return hit
            statement = ctx.years_statement_fr if ctx.language == "fr" else ctx.years_statement
            bad = [c for c, _v in years_claims(sentence)] if statement else []
            bad = [c for c in bad if statement.lower() not in c.lower()]
            if statement and bad and statement.lower() not in sentence.lower():
                fixed = sentence
                for claim in bad:
                    fixed = fixed.replace(claim, statement, 1)
                return fixed, f"Years wording: “{statement}”"
        if quote:
            if hit := self._number(sentence, quote):
                return hit
            if hit := self._tool(sentence, quote):
                return hit
        return self._name(row)

    def _banned(self, sentence: str) -> tuple[str, str] | None:
        fixed = sentence
        for phrase in self.ctx.banned:
            pattern = re.compile(rf"\b{re.escape(phrase.replace('’', chr(39)))}\b[,;]?\s*", re.I)
            fixed = pattern.sub("", fixed.replace("’", "'"))
        fixed = re.sub(r"\s{2,}", " ", fixed).strip()
        if fixed == sentence or len(fixed.split()) < 3:
            return None
        return fixed[0].upper() + fixed[1:], "Banned phrase removed"

    @staticmethod
    def _number(sentence: str, quote: str) -> tuple[str, str] | None:
        right = {re.sub(r"\s", "", n) for n in numbers(quote)}
        wrong = [n for n in dict.fromkeys(numbers(sentence)) if n not in right]
        spare = [n for n in right if n not in numbers(sentence)]
        if len(wrong) == 1 and len(spare) == 1:
            return sentence.replace(wrong[0], spare[0], 1), f"Number from the source: {spare[0]}"
        return None

    @staticmethod
    def _tool(sentence: str, quote: str) -> tuple[str, str] | None:
        source_words = Vocabulary(quote)
        wrong = new_tools(sentence, source_words)
        spare = [t for t in new_tools(quote, Vocabulary(sentence))]
        if len(wrong) == 1 and len(spare) == 1 and wrong[0] in sentence:
            return sentence.replace(wrong[0], spare[0], 1), f"Tool from the source: {spare[0]}"
        return None

    def _name(self, row: dict[str, Any]) -> tuple[str, str] | None:
        """A greeting with no name, or the wrong one, gets the contact in RECIPIENT."""
        m = re.search(r"^Contact: ([^,\n]+)", self.sources.get("recipient", ""), re.M)
        if not m:
            return None
        full = m.group(1).strip()
        greeting = re.match(r"^(Hi|Hello|Dear|Hey|Bonjour|Salut)\b[ ]*([^,\n]*),?$",
                            row["sentence"].strip(), re.I)
        if not greeting or full.lower() in greeting.group(2).lower():
            return None
        word = greeting.group(1)
        name = full if word.lower() in ("dear", "bonjour") else full.split()[0]
        return f"{word} {name},", f"Name from the contact: {name}"

    # ----------------------------------------------------------------------- the fix
    def fix(self, row: dict[str, Any]) -> dict[str, str]:
        found = self.deterministic(row)
        if found and found[0].strip() and found[0] != row["sentence"] \
                and not self.problems(found[0]):
            return _fix(REPLACE, found[0], origin="code", note=found[1],
                        source_id=row.get("source_id") or "",
                        source_quote=row.get("source_quote") or "")
        suggestion = (row.get("suggestion") or "").strip()
        if not suggestion:
            return _fix(REMOVE, origin="claude",
                        note="Nothing in your sources supports it: remove the sentence")
        source = self.sources.get(row.get("suggestion_source_id") or "")
        quote = (row.get("suggestion_quote") or "").strip()
        if source is None or not quote or vf._norm(quote) not in vf._norm(source):
            return _fix(REMOVE, origin="checks",
                        note="The suggested wording had no real source quote: remove the sentence")
        if problems := self.problems(suggestion):
            return _fix(REMOVE, origin="checks",
                        note=f"The suggested wording failed the checks ({problems[0]}): remove "
                             "the sentence")
        if vf._norm(suggestion) == vf._norm(row["sentence"]):
            return _fix(REMOVE, origin="checks", note="The suggestion repeated the sentence")
        return _fix(REPLACE, suggestion, origin="claude",
                    note="Only what your sources state",
                    source_id=row["suggestion_source_id"], source_quote=quote)


def for_application(s: Session, app: Application, sources: dict[str, str],
                    language: str = "en") -> Fixer:
    from app.services import cover_letter as cl

    try:
        ctx = cl.context(s, app, language)
    except Exception:  # noqa: BLE001 - a missing piece of context must never break verification
        ctx = None
    return Fixer(sources=sources, ctx=ctx)


def attach(rows: list[dict[str, Any]], fixer: Fixer | None, blocking: set[str]) -> None:
    """Put a `fix` on every blocking claim (the model's raw suggestion fields are dropped)."""
    for row in rows:
        if row["verdict"] in blocking and not row.get("skipped") and fixer is not None:
            row["fix"] = fixer.fix(row)
        for key in ("suggestion", "suggestion_source_id", "suggestion_quote"):
            row.pop(key, None)


# ------------------------------------------------------------------------------- applying

def replace_sentence(text: str, sentence: str, replacement: str) -> str:
    """The text with one sentence replaced (or removed when `replacement` is empty)."""
    if sentence not in text:
        raise FixError("That sentence is no longer in the text: check the claims again")
    out = text.replace(sentence, replacement.strip(), 1)
    if not replacement.strip():
        out = re.sub(r"[ \t]{2,}", " ", out)
        out = re.sub(r"\n[ \t]+", "\n", out)
        out = re.sub(r"\n{3,}", "\n\n", out)
    return out.strip()


def merge(record: dict[str, Any], replaced: dict[str, list[dict[str, Any]]], text: str,
          attachment_sha256: str | None) -> dict[str, Any]:
    """The old record with the claims of the replaced sentences swapped for their new verdicts,
    tied to the new text (so a partial re-verification can pass the whole text)."""
    claims: list[dict[str, Any]] = []
    done: set[str] = set()
    for c in record.get("claims") or []:
        if c["sentence"] in replaced:
            if c["sentence"] not in done:
                claims += replaced[c["sentence"]]
                done.add(c["sentence"])
            continue
        claims.append(c)
    blocking = [c for c in claims if c["verdict"] in vf.BLOCKING]
    return {**record, "claims": claims, "blocking": len(blocking),
            "status": "failed" if blocking else "passed", "hash": vf.text_hash(text),
            "attachment_sha256": attachment_sha256, "at": vf.utcnow().isoformat(),
            "partial": True}


def _guard(record: dict[str, Any] | None, text: str, fixes: list[tuple[str, str]]) -> None:
    """The fixes belong to a check of exactly this text: never merge them into a stale one."""
    if not record or record.get("status") not in ("passed", "failed") \
            or record.get("hash") != vf.text_hash(text):
        raise FixError("The text changed since the last check: check the claims again first")
    for sentence, _ in fixes:
        if sentence not in text:
            raise FixError("That sentence isn't in the text any more: check the claims again")


def _edit_email(s: Session, draft: Any, fixes: list[tuple[str, str]]) -> None:
    from app.models.enums import DraftStatus
    from app.services import outreach

    if draft.status not in (DraftStatus.draft, DraftStatus.rejected):
        raise FixError("Only drafts under review can be edited")
    subject, body = draft.subject, draft.body
    for sentence, replacement in fixes:
        if sentence in (subject, f"Subject: {subject}"):
            new = re.sub(r"^Subject:\s*", "", replacement.strip())
            if not new:
                raise FixError("The subject can't be removed: edit it")
            subject = new
        elif sentence in body:
            body = replace_sentence(body, sentence, replacement)
        else:
            raise FixError("That part (the signature or footer) isn't edited here")
    draft.subject, draft.body, draft.edited = subject, body, True
    draft.violations = outreach.recheck(s, draft)
    s.add(draft)


def _edit_letter(s: Session, letter: Any, fixes: list[tuple[str, str]]) -> None:
    from app.models.enums import CVStatus
    from app.services import cover_letter as cl

    if letter.locked_at is not None or letter.status == CVStatus.superseded:
        raise FixError("This version is locked: make a new draft first")
    content = dict(letter.content or {})
    paragraphs = [cl.paragraph_text(p) for p in content.get("paragraphs") or []]
    ask = str(content.get("ask") or "").strip()
    salutation = str(content.get("salutation") or "").strip()
    for sentence, replacement in fixes:
        if sentence == salutation:
            salutation = replacement.strip()
            continue
        for i, text in enumerate(paragraphs):
            if sentence in text:
                paragraphs[i] = replace_sentence(text, sentence, replacement)
                break
        else:
            if sentence not in ask:
                raise FixError("That part (the closing or your name) isn't edited here")
            ask = replace_sentence(ask, sentence, replacement)
    cl.edit(s.get_bind(), letter.id, salutation=salutation, paragraphs=paragraphs, ask=ask)  # type: ignore[arg-type]


def apply(s: Session, kind: str, target_id: int, sub: str, fixes: list[tuple[str, str]],
          verifier: Any) -> dict[str, Any]:
    """Apply fixes (sentence → replacement, "" removes it) to a document, then verify ONLY the
    changed sentences and merge the verdicts into the stored record. Returns the new record."""
    from app.models import ApplicationAnswer, CoverLetter, LinkedInOutreach, OutreachDraft
    from app.services import answers, linkedin_track

    fixes = list(dict(fixes).items())  # one fix per sentence
    if not fixes:
        raise FixError("Nothing to apply")
    holder: Any
    if kind == "email":
        holder = s.get(OutreachDraft, target_id)
        if holder is None:
            raise FixError("Draft not found")
        _guard(holder.verification, vf.email_text(s, holder), fixes)
        _edit_email(s, holder, fixes)
        prep = vf.prepare_email(s, holder)
    elif kind == "letter":
        holder = s.get(CoverLetter, target_id)
        if holder is None:
            raise FixError("Cover letter not found")
        _guard(holder.verification, vf.letter_text(s, holder), fixes)
        _edit_letter(s, holder, fixes)
        s.commit()
        s.refresh(holder)
        prep = vf.prepare_letter(s, holder)
    elif kind == "answer":
        holder = s.get(ApplicationAnswer, target_id)
        if holder is None:
            raise FixError("Answer not found")
        _guard(holder.verification, holder.answer, fixes)
        text = holder.answer
        for sentence, replacement in fixes:
            text = replace_sentence(text, sentence, replacement)
        if not text.strip():
            raise FixError("That would leave the answer empty: edit it instead")
        answers.update(s, holder, text=text)
        prep = vf.prepare_answer(s, holder)
    elif kind == "linkedin":
        holder = s.get(LinkedInOutreach, target_id)
        if holder is None or sub not in ("note", "followup", "inmail"):
            raise FixError("Message not found")
        message = dict(getattr(holder, sub) or {})
        text, subject = str(message.get("text") or ""), str(message.get("subject") or "")
        from app.services.linkedin_check import inmail_text

        _guard(message.get("verification"), inmail_text(message) if sub == "inmail" else text,
               fixes)
        for sentence, replacement in fixes:
            if sub == "inmail" and sentence in (subject, f"Subject: {subject}"):
                subject = re.sub(r"^Subject:\s*", "", replacement.strip())
                if not subject:
                    raise FixError("The subject can't be removed: edit it")
            else:
                text = replace_sentence(text, sentence, replacement)
        if not text.strip():
            raise FixError("That would leave the message empty: edit it instead")
        linkedin_track.edit(s, holder, sub, text=text, subject=subject if sub == "inmail" else None)
        prep = vf.prepare_linkedin(s, holder, sub)
    else:
        raise FixError("kind is email, letter, answer or linkedin")

    old = _record(holder, kind, sub)
    changed = {sentence: vf.sentences(replacement) for sentence, replacement in fixes}
    fresh: dict[str, list[dict[str, Any]]] = {}
    for sentence, new_sentences in changed.items():
        fresh[sentence] = []
        if not new_sentences:
            continue
        record = prep.run(verifier, "\n".join(new_sentences))
        if record["status"] == "error":
            raise FixError(f"The claim verifier couldn't run ({record.get('error')}): "
                           "the text was changed, check the claims again")
        fresh[sentence] = record["claims"]
    merged = merge(old, fresh, prep.text, prep.attachment)
    _store(holder, kind, sub, merged)
    s.add(holder)
    s.commit()
    return merged


def _record(holder: Any, kind: str, sub: str) -> dict[str, Any]:
    if kind == "linkedin":
        return dict((getattr(holder, sub) or {}).get("verification") or {})
    return dict(holder.verification or {})


def _store(holder: Any, kind: str, sub: str, record: dict[str, Any]) -> None:
    if kind == "linkedin":
        message = dict(getattr(holder, sub) or {})
        message["verification"] = record
        setattr(holder, sub, message)
    else:
        holder.verification = record
