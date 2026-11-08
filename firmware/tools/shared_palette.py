"""Experimental native NES palettes with 2/3/4 shared colours.

Offline only. Keeps the 16x16 attribute format and does not add dithering.
Fit a whole shot, then use scene_palette.encode_fixed for individual frames.
"""
import numpy as np
import nesframe as nf
from scene_palette import quant


def choose_shared_palette(images, shared=2, initial=None):
    if shared not in (2, 3, 4):
        raise ValueError('shared must be 2, 3, or 4')
    hist = np.zeros((240, 64), dtype=np.float64)
    blocks = (np.arange(240)[:, None] // 16) * 16 + np.arange(256)[None, :] // 16
    for image in images:
        near = nf.NEAR_LUT[quant(image)]
        hist += np.bincount((blocks * 64 + near).ravel(), minlength=240*64).reshape(240, 64)
    candidates = np.asarray(nf.USABLE)
    total = hist.sum(0)
    # Deterministic global four-colour seed, using all legal NES candidates.
    seed = [int(candidates[np.argmin(total @ nf.PT[:, candidates])])]
    while len(seed) < 4:
        costs = total @ np.minimum(nf.PT[:, seed].min(1)[:, None], nf.PT[:, candidates])
        costs[np.isin(candidates, seed)] = np.inf
        seed.append(int(candidates[costs.argmin()]))
    starts = [np.tile(seed, (4, 1))]
    if initial is not None:
        p = np.asarray(initial[:16], dtype=int).reshape(4, 4).copy()
        # Retain the original common background plus globally useful tones.
        common = [int(p[0, 0])] + [c for c in seed if c != p[0, 0]]
        p[:, :shared] = common[:shared]
        starts.append(p)
    best = None
    for p in starts:
        for _ in range(16):
            error = hist @ nf.PT[:, p].min(-1)
            assignment = error.argmin(1)
            grouped = np.stack([hist[assignment == k].sum(0) for k in range(4)])
            old = p.copy()
            # Shared slots optimise all four clusters; private slots optimise one.
            for slot in range(4):
                groups = [range(4)] if slot < shared else [[k] for k in range(4)]
                for affected in groups:
                    costs = np.zeros(len(candidates))
                    for k in affected:
                        others = np.delete(p[k], slot)
                        d = np.minimum(nf.PT[:, others].min(1)[:, None], nf.PT[:, candidates])
                        costs += grouped[k] @ d
                    colour = int(candidates[costs.argmin()])
                    for k in affected:
                        p[k, slot] = colour
            if np.array_equal(old, p):
                break
        cost = float((hist @ nf.PT[:, p].min(-1)).min(1).sum())
        if best is None or cost < best[0]:
            best = cost, p.copy()
    p = best[1]
    assert (p[:, :shared] == p[0, :shared]).all()
    palette = p.ravel().tolist() + [int(p[0, 0]), 0x30, 0x0f, 0x0f]*4
    return palette, p[:, 1:], {'shared': shared, 'unique': len(set(p.ravel().tolist())), 'fit_cost': best[0]}


def choose_context_palette(images, initial, margin=4):
    """Fit palettes to overlapping regions, retaining the normal 13-colour budget."""
    if not 0 <= margin <= 16:
        raise ValueError('margin must be between 0 and 16')
    hist = np.zeros((15, 16, 64), dtype=np.int64)
    for image in images:
        near = nf.NEAR_LUT[quant(image)]
        for y in range(15):
            for x in range(16):
                region = near[max(0,y*16-margin):min(240,(y+1)*16+margin),
                              max(0,x*16-margin):min(256,(x+1)*16+margin)]
                hist[y,x] += np.bincount(region.ravel(), minlength=64)
    best = None
    backgrounds = list(dict.fromkeys([int(initial[0])] + np.argsort(-hist.sum((0,1)))[:3].tolist()))
    for bg in backgrounds:
        pals, _, cost = nf._search_palettes(hist, bg, False, 0, 10,
                         np.asarray(initial[:16]).reshape(4,4)[:,1:].tolist(), mix=False)
        if best is None or cost < best[0]:
            best = cost, bg, pals
    _, bg, pals = best
    palette = sum(([int(bg)]+list(map(int,p)) for p in pals),[]) + [int(bg),0x30,0x0f,0x0f]*4
    return palette, np.asarray(pals), {'margin':margin, 'fit_cost':float(best[0])}
