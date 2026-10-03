"""Motivation (Phase 11): streak, chests, tokens and shop, and the Motiv Center. Reads job data,
writes only its own tables; `motivation.enabled` (Settings) hides it all in the app."""

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlmodel import col, func, select

from app.api.deps import SessionDep, WorkspaceDep, get_or_404
from app.models import GoalTile, Purchase, ShopItem, WinEntry, Woop
from app.schemas.motivation import (
    ChestOpenOut,
    ChestsOut,
    GoalTileOut,
    GoalTilePatch,
    ImageOut,
    OpenedOut,
    OrderIn,
    PurchaseOut,
    RedeemIn,
    ShopItemIn,
    ShopItemOut,
    ShopItemPatch,
    ShopOut,
    StreakOut,
    SuggestionOut,
    SummaryOut,
    TokenEntryOut,
    TokensOut,
    WinIn,
    WinOut,
    WinsOut,
    WoopIn,
    WoopOut,
)
from app.services import motivation as mv
from app.services.motivation import activity, files, insights, rewards
from app.services.motivation.streak import compute

router = APIRouter(tags=["motivation"])


def _out(model, row):  # noqa: ANN001, ANN202
    return model.model_validate(row, from_attributes=True)


def _streak(session, cfg: dict, calendar: bool) -> StreakOut:  # noqa: ANN001
    st = compute(activity.per_day(session, cfg), mv.today(cfg), cfg["daily_goal"])
    out = StreakOut.model_validate(st, from_attributes=True)
    return out if calendar else out.model_copy(update={"calendar": []})


def _chests(session, cfg: dict) -> ChestsOut:  # noqa: ANN001
    return _out(ChestsOut, rewards.chests(session, cfg))


@router.get("/motivation/summary", response_model=SummaryOut)
def summary(session: SessionDep) -> SummaryOut:
    """The top bar and Today: streak, today's progress, tokens, chests."""
    cfg = mv.settings(session)
    return SummaryOut(enabled=bool(cfg["enabled"]), streak=_streak(session, cfg, True),
                      tokens=rewards.balance(session), chests=_chests(session, cfg))


@router.get("/motivation/chests", response_model=list[ChestOpenOut])
def chest_history(session: SessionDep) -> list[ChestOpenOut]:
    return [_out(ChestOpenOut, r) for r in rewards.history(session)]


@router.post("/motivation/chests/open", response_model=OpenedOut)
def open_chest(session: SessionDep) -> OpenedOut:
    cfg = mv.settings(session)
    try:
        row = rewards.open_chest(session, cfg)
    except rewards.RewardError as exc:
        raise HTTPException(409, str(exc)) from exc
    return OpenedOut(chest=_out(ChestOpenOut, row), balance=rewards.balance(session),
                     chests=_chests(session, cfg))


@router.get("/motivation/tokens", response_model=TokensOut)
def tokens(session: SessionDep) -> TokensOut:
    return TokensOut(balance=rewards.balance(session),
                     ledger=[_out(TokenEntryOut, e) for e in rewards.ledger(session)])


# --------------------------------------------------------------------------------- shop


def _shop(session) -> ShopOut:  # noqa: ANN001
    return ShopOut(balance=rewards.balance(session),
                   items=[_out(ShopItemOut, i) for i in rewards.items(session, archived=True)],
                   purchases=[_out(PurchaseOut, p) for p in rewards.purchases(session)])


@router.get("/motivation/shop", response_model=ShopOut)
def shop(session: SessionDep) -> ShopOut:
    return _shop(session)


@router.post("/motivation/shop", response_model=ShopOut, status_code=201)
def add_item(body: ShopItemIn, session: SessionDep) -> ShopOut:
    try:
        rewards.save_item(session, None, name=body.name, price=body.price, emoji=body.emoji,
                          image_name=body.image_name)
    except rewards.RewardError as exc:
        raise HTTPException(422, str(exc)) from exc
    return _shop(session)


@router.patch("/motivation/shop/{item_id}", response_model=ShopOut)
def edit_item(item_id: int, body: ShopItemPatch, session: SessionDep) -> ShopOut:
    item = get_or_404(session, ShopItem, item_id, "Item")
    if body.archived is not None:
        item.archived = body.archived
    fields = body.model_fields_set - {"archived"}
    if fields:
        try:
            rewards.save_item(
                session, item, name=body.name if body.name is not None else item.name,
                price=body.price if body.price is not None else item.price,
                emoji=body.emoji if "emoji" in fields else item.emoji,
                image_name=body.image_name if "image_name" in fields else item.image_name)
        except rewards.RewardError as exc:
            raise HTTPException(422, str(exc)) from exc
    session.add(item)
    session.commit()
    return _shop(session)


@router.post("/motivation/shop/{item_id}/buy", response_model=ShopOut)
def buy(item_id: int, session: SessionDep) -> ShopOut:
    item = get_or_404(session, ShopItem, item_id, "Item")
    try:
        rewards.buy(session, item)
    except rewards.RewardError as exc:
        raise HTTPException(409, str(exc)) from exc
    return _shop(session)


@router.patch("/motivation/purchases/{purchase_id}", response_model=ShopOut)
def redeem(purchase_id: int, body: RedeemIn, session: SessionDep) -> ShopOut:
    row = get_or_404(session, Purchase, purchase_id, "Purchase")
    rewards.set_redeemed(session, row, body.redeemed)
    return _shop(session)


# ------------------------------------------------------------------------------- files


async def _read(file: UploadFile, max_mb: int) -> bytes:
    data = await file.read(max_mb * 1024 * 1024 + 1)  # one byte over the limit is enough
    if len(data) > max_mb * 1024 * 1024:
        raise HTTPException(413, f"The file is larger than the {max_mb} MB limit (Settings → "
                                 "Motivation)")
    return data


@router.post("/motivation/images", response_model=ImageOut, status_code=201)
async def upload_image(session: SessionDep, workspace: WorkspaceDep,
                       file: UploadFile = File(...)) -> ImageOut:
    """An image for a shop item (images only)."""
    cfg = mv.settings(session)
    data = await _read(file, int(cfg["max_upload_mb"]))
    try:
        _kind, ext, _mime = files.check(file.filename or "", data[:16], len(data),
                                        int(cfg["max_upload_mb"]), images_only=True)
    except files.UploadError as exc:
        raise HTTPException(exc.status, str(exc)) from exc
    return ImageOut(name=files.save(workspace, ext, data))


@router.get("/motivation/files/{name}")
def get_file(name: str, workspace: WorkspaceDep) -> FileResponse:
    path = files.path(workspace, name)
    if path is None:
        raise HTTPException(404, "File not found")
    return FileResponse(path, media_type=files.mime(name),
                        headers={"Cache-Control": "private, max-age=86400"})


# -------------------------------------------------------------------------- my goals


@router.get("/motivation/goals", response_model=list[GoalTileOut])
def goals(session: SessionDep) -> list[GoalTileOut]:
    rows = session.exec(select(GoalTile).order_by(col(GoalTile.position), col(GoalTile.id)))
    return [_out(GoalTileOut, t) for t in rows.all()]


@router.post("/motivation/goals", response_model=GoalTileOut, status_code=201)
async def add_goal(session: SessionDep, workspace: WorkspaceDep, file: UploadFile = File(...),
                   caption: str = Form("")) -> GoalTileOut:
    cfg = mv.settings(session)
    data = await _read(file, int(cfg["max_upload_mb"]))
    try:
        kind, ext, mime = files.check(file.filename or "", data[:16], len(data),
                                      int(cfg["max_upload_mb"]))
    except files.UploadError as exc:
        raise HTTPException(exc.status, str(exc)) from exc
    last = session.exec(select(func.coalesce(func.max(GoalTile.position), 0))).one()
    tile = GoalTile(kind=kind, file_name=files.save(workspace, ext, data),
                    original_name=(file.filename or "")[:200], mime=mime, size=len(data),
                    caption=caption.strip(), position=int(last) + 1)
    session.add(tile)
    session.commit()
    session.refresh(tile)
    return _out(GoalTileOut, tile)


@router.patch("/motivation/goals/{tile_id}", response_model=GoalTileOut)
def edit_goal(tile_id: int, body: GoalTilePatch, session: SessionDep) -> GoalTileOut:
    tile = get_or_404(session, GoalTile, tile_id, "Tile")
    tile.caption = body.caption.strip()
    session.add(tile)
    session.commit()
    session.refresh(tile)
    return _out(GoalTileOut, tile)


@router.put("/motivation/goals/order", response_model=list[GoalTileOut])
def order_goals(body: OrderIn, session: SessionDep) -> list[GoalTileOut]:
    tiles = {t.id: t for t in session.exec(select(GoalTile)).all()}
    if set(body.ids) != set(tiles):
        raise HTTPException(422, "Send every tile id once")
    for position, tile_id in enumerate(body.ids, 1):
        tiles[tile_id].position = position
        session.add(tiles[tile_id])
    session.commit()
    return goals(session)


@router.delete("/motivation/goals/{tile_id}", status_code=204)
def delete_goal(tile_id: int, session: SessionDep, workspace: WorkspaceDep) -> None:
    tile = get_or_404(session, GoalTile, tile_id, "Tile")
    files.remove(workspace, tile.file_name)
    session.delete(tile)
    session.commit()


# ------------------------------------------------------------------- plan, wins, start


@router.get("/motivation/woops", response_model=list[WoopOut])
def woops(session: SessionDep) -> list[WoopOut]:
    rows = session.exec(select(Woop).order_by(col(Woop.created_at).desc())).all()
    return [_out(WoopOut, w) for w in rows]


@router.post("/motivation/woops", response_model=WoopOut, status_code=201)
def add_woop(body: WoopIn, session: SessionDep) -> WoopOut:
    if not body.wish.strip():
        raise HTTPException(422, "Start with your wish")
    row = Woop(**{k: v.strip() for k, v in body.model_dump().items()})
    session.add(row)
    session.commit()
    session.refresh(row)
    return _out(WoopOut, row)


@router.delete("/motivation/woops/{woop_id}", status_code=204)
def delete_woop(woop_id: int, session: SessionDep) -> None:
    session.delete(get_or_404(session, Woop, woop_id, "WOOP"))
    session.commit()


@router.get("/motivation/wins", response_model=WinsOut)
def wins(session: SessionDep) -> WinsOut:
    cfg = mv.settings(session)
    journal = session.exec(select(WinEntry).order_by(col(WinEntry.created_at).desc())).all()
    return WinsOut(**insights.wins(session, cfg), journal=[_out(WinOut, w) for w in journal])


@router.post("/motivation/journal", response_model=WinOut, status_code=201)
def add_win(body: WinIn, session: SessionDep) -> WinOut:
    if not body.text.strip():
        raise HTTPException(422, "Write your win first")
    row = WinEntry(text=body.text.strip()[:1000])
    session.add(row)
    session.commit()
    session.refresh(row)
    return _out(WinOut, row)


@router.delete("/motivation/journal/{win_id}", status_code=204)
def delete_win(win_id: int, session: SessionDep) -> None:
    session.delete(get_or_404(session, WinEntry, win_id, "Win"))
    session.commit()


@router.get("/motivation/suggestion", response_model=SuggestionOut)
def suggestion(session: SessionDep) -> SuggestionOut:
    return SuggestionOut(**insights.suggestion(session))
