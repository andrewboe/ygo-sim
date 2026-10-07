"""The neural pilot (THEORY §5): one network for every deck.

Inputs are ygoenv's observation tensors (lite=False):
  cards_     [150, 40] uint8  per card: id (2 bytes, code-list id), location, sequence, opponent flag,
                              position, face-up flag, attribute, race, level, counters, ATK (2 bytes),
                              DEF (2 bytes), type ids (cols 15+). Empty slots are all zero.
  global_    [9]      uint8   my LP (2 bytes), opponent LP (2 bytes), turn, phase, went first, my turn
  actions_   [24, 20] uint8   per option: 5 card references (2 bytes each, 1-based slot in cards_, 0 =
                              none), then decision type, action, yes/no, phase, cancel/finish, position,
                              option, number, zone, attribute
Architecture: card tokens (embeddings) + a global token -> transformer encoder; each option is scored
from its own feature embeddings plus the encoded tokens of the cards it references; value from the
encoded global token.
"""
import torch
import torch.nn as nn
import torch.nn.functional as F

N_CARD_IDS = 1 << 15   # code-list ids (~15k cards today); headroom for new sets
CARD_TYPE_COLS = slice(15, 40)
N_SPEC = 5             # card references per option (max_multi_select)


class Pilot(nn.Module):
    def __init__(self, dim: int = 128, layers: int = 4, heads: int = 4):
        super().__init__()
        self.card_id = nn.Embedding(N_CARD_IDS, dim)
        # Small categorical card fields (cols 2..10): location, seq, opponent, position, face-up,
        # attribute, race, level, counters. One shared table, offset per field.
        self.card_cat = nn.Embedding(9 * 256, dim)
        self.card_type = nn.EmbeddingBag(256, dim, mode="sum", padding_idx=0)
        self.card_num = nn.Linear(4, dim)  # ATK/DEF bytes
        self.glob_cat = nn.Embedding(5 * 256, dim)  # turn, phase, went first, my turn, no-options flag
        self.glob_num = nn.Linear(4, dim)            # LP bytes
        enc = nn.TransformerEncoderLayer(dim, heads, 4 * dim, dropout=0.0, batch_first=True, norm_first=True)
        self.encoder = nn.TransformerEncoder(enc, layers)
        self.opt_cat = nn.Embedding(10 * 256, dim)  # option feature cols 10..19
        self.opt_mlp = nn.Sequential(nn.Linear(3 * dim, dim), nn.GELU(), nn.Linear(dim, 1))
        self.value = nn.Sequential(nn.Linear(dim, dim), nn.GELU(), nn.Linear(dim, 1))
        self.register_buffer("cat_offsets", torch.arange(9) * 256)
        self.register_buffer("glob_offsets", torch.arange(5) * 256)
        self.register_buffer("opt_offsets", torch.arange(10) * 256)

    def forward(self, cards, glob, actions, num_options):
        cards, glob, actions = cards.long(), glob.long(), actions.long()
        b = cards.shape[0]
        card_ids = (cards[..., 0] << 8) | cards[..., 1]
        empty = cards[..., 2] == 0  # no location -> empty slot
        tok = (self.card_id(card_ids.clamp(max=N_CARD_IDS - 1))
               + self.card_cat(cards[..., 2:11] + self.cat_offsets).sum(-2)
               + self.card_type(cards[..., CARD_TYPE_COLS].reshape(-1, 25)).view(b, -1, tok_dim(self))
               + self.card_num(cards[..., 11:15].float() / 255))
        g = (self.glob_cat(glob[:, 4:9] + self.glob_offsets).sum(-2)
             + self.glob_num(glob[:, 0:4].float() / 255)).unsqueeze(1)
        x = torch.cat([g, tok], 1)
        mask = torch.cat([torch.zeros(b, 1, dtype=torch.bool, device=x.device), empty], 1)
        x = self.encoder(x, src_key_padding_mask=mask)
        g_out, card_out = x[:, 0], x[:, 1:]

        # Options: own features + mean of referenced cards' encodings.
        refs = (actions[..., 0:2 * N_SPEC:2] << 8) | actions[..., 1:2 * N_SPEC:2]  # [b, opts, 5], 1-based
        valid_ref = refs > 0
        idx = (refs - 1).clamp(min=0, max=card_out.shape[1] - 1)
        gathered = torch.gather(card_out.unsqueeze(1).expand(-1, refs.shape[1], -1, -1), 2,
                                idx.unsqueeze(-1).expand(-1, -1, -1, card_out.shape[-1]))
        ref_mean = (gathered * valid_ref.unsqueeze(-1)).sum(2) / valid_ref.sum(2, keepdim=True).clamp(min=1)
        opt = self.opt_cat(actions[..., 10:20] + self.opt_offsets).sum(-2)
        logits = self.opt_mlp(torch.cat([opt, ref_mean, g_out.unsqueeze(1).expand_as(opt)], -1)).squeeze(-1)
        option_mask = torch.arange(logits.shape[1], device=logits.device)[None] < num_options[:, None]
        logits = logits.masked_fill(~option_mask, float("-inf"))
        return logits, self.value(g_out).squeeze(-1)


def tok_dim(m: Pilot) -> int:
    return m.card_id.embedding_dim


def loss_fn(logits, value, action, value_target, value_weight: float = 0.1):
    policy = F.cross_entropy(logits, action)
    return policy + value_weight * F.mse_loss(value, value_target), policy
