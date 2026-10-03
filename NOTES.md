# Notes

## Walking after a teleport (removed, for later)

Help-off steps used to walk the player forward left for 0.5s after the teleport, so they don't start exactly on the spot.
cfg has no delay, so a `point_servercommand` presses the keys from delayed player outputs. Own file (`kt/walk.cfg`, run with
`exec kt/walk` after the `setpos`): `ent_create` needs quotes, which an alias can't hold.

```
ent_fire kt_sc kill
ent_create point_servercommand {"targetname" "kt_sc"}
ent_fire player AddOutput "OnUser2>kt_sc>Command>+forward>0.10>1"
ent_fire player AddOutput "OnUser2>kt_sc>Command>-forward>0.60>1"
ent_fire player AddOutput "OnUser2>kt_sc>Command>+left>0.10>1"
ent_fire player AddOutput "OnUser2>kt_sc>Command>-left>0.60>1"
ent_fire player FireUser2
```

CS2 strafes with `left`/`right` (no `moveleft`). Walking instead of a shifted `setpos` keeps the player out of walls and floors.
Issues: own movement keys during the walk fight with it, a corner blocking forward left barely moves you. Skip it on spawn steps.
