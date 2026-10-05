"""Entrena embeddings de producto con PyTorch (item2vec: skip-gram con muestreo negativo sobre tickets).

Idea: dos productos que aparecen juntos en muchos tickets acaban con vectores parecidos
("pasta" cerca de "tomate frito"). Con esos vectores representamos también los gustos del cliente.

  python -m app.recsys.train          (requiere requirements-train.txt)

Salida: models/item_embeddings.npy + models/item_ids.json -> el servicio los sirve con numpy (sin PyTorch).
En producción lo lanzaría un job nocturno de Spring Batch tras ingerir los tickets del día.
"""
from __future__ import annotations

import json
import time

import numpy as np
import torch
from torch import nn

from app.config import settings
from app.db import query_df

DIM, EPOCHS, BATCH, NEG, LR, MAX_BASKET = 32, 6, 4096, 10, 0.01, 30
SUBSAMPLE_T = 1e-3  # submuestreo estilo word2vec: descarta pares de productos muy frecuentes (pan, leche...)


class Item2Vec(nn.Module):
    def __init__(self, n: int, dim: int):
        super().__init__()
        self.inp = nn.Embedding(n, dim)
        self.out = nn.Embedding(n, dim)
        nn.init.normal_(self.inp.weight, std=0.1)
        nn.init.zeros_(self.out.weight)

    def forward(self, center, context, negatives):
        c = self.inp(center)                                  # (B, D)
        pos = (c * self.out(context)).sum(-1)                 # (B,)
        neg = torch.bmm(self.out(negatives), c.unsqueeze(-1)).squeeze(-1)  # (B, NEG)
        return -(nn.functional.logsigmoid(pos) + nn.functional.logsigmoid(-neg).sum(-1)).mean()


def build_pairs(rng: np.random.Generator) -> tuple[np.ndarray, list[str], np.ndarray]:
    df = query_df("""SELECT l.ticket_id, l.producto_id FROM lineas_ticket l
                     JOIN productos p ON p.id = l.producto_id WHERE p.sensible = :f""", f=False)
    ids = sorted(df.producto_id.unique())
    idx = {p: i for i, p in enumerate(ids)}
    pairs = []
    for _, items in df.groupby("ticket_id").producto_id:
        it = [idx[p] for p in set(items)]
        if len(it) > MAX_BASKET:
            it = list(rng.choice(it, MAX_BASKET, replace=False))
        for a in it:
            for b in it:
                if a != b:
                    pairs.append((a, b))
    counts = np.bincount(df.producto_id.map(idx), minlength=len(ids)).astype(float)
    return np.array(pairs, dtype=np.int64), ids, counts


def main() -> None:
    t0 = time.time()
    torch.manual_seed(0)
    rng = np.random.default_rng(0)
    pairs, ids, counts = build_pairs(rng)
    freq = counts / counts.sum()
    keep = np.minimum(1.0, np.sqrt(SUBSAMPLE_T / freq))
    pairs = pairs[rng.random(len(pairs)) < keep[pairs[:, 0]] * keep[pairs[:, 1]]]
    noise = torch.tensor(counts ** 0.75 / (counts ** 0.75).sum(), dtype=torch.float)
    model = Item2Vec(len(ids), DIM)
    opt = torch.optim.Adam(model.parameters(), lr=LR)
    data = torch.from_numpy(pairs)
    print(f"{len(ids)} productos | {len(pairs):,} pares de co-compra (tras submuestreo)")
    for ep in range(EPOCHS):
        perm = torch.randperm(len(data))
        total = 0.0
        for i in range(0, len(data), BATCH):
            b = data[perm[i:i + BATCH]]
            negs = torch.multinomial(noise, len(b) * NEG, replacement=True).view(len(b), NEG)
            loss = model(b[:, 0], b[:, 1], negs)
            opt.zero_grad()
            loss.backward()
            opt.step()
            total += loss.item() * len(b)
        print(f"  época {ep + 1}/{EPOCHS}  pérdida {total / len(data):.4f}")
    emb = (model.inp.weight + model.out.weight).detach().numpy()  # combinar entrada+salida da vecinos más coherentes
    emb = emb / np.linalg.norm(emb, axis=1, keepdims=True)
    settings.models_dir.mkdir(exist_ok=True)
    np.save(settings.models_dir / "item_embeddings.npy", emb.astype(np.float32))
    (settings.models_dir / "item_ids.json").write_text(json.dumps(ids))
    print(f"Guardado en {settings.models_dir} ({time.time() - t0:.1f} s)")


if __name__ == "__main__":
    main()
