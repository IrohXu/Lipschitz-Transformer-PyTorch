import torch
import torch.nn as nn
from torch.nn.utils import spectral_norm
from einops import rearrange


class L2Attention(nn.Module):
    def __init__(self, dim, num_heads=8, qkv_bias=False, attn_drop=0., proj_drop=0., sn=False):
        super().__init__()
        assert dim % num_heads == 0, 'dim should be divisible by num_heads'
        self.num_heads = num_heads
        head_dim = dim // num_heads
        self.scale = head_dim ** -0.5

        self.sn = sn

        if sn:
            self.qkv = spectral_norm(nn.Linear(dim, dim * 2, bias=qkv_bias))
        else:
            self.qkv = nn.Linear(dim, dim * 2, bias=qkv_bias)
        self.attn_drop = nn.Dropout(attn_drop)

        self.proj = nn.Linear(dim, dim)
        self.proj_drop = nn.Dropout(proj_drop)

    def forward(self, x):
        assert x.dim() == 3  # b t c
        # Generate the q, k, v vectors
        qkv = self.qkv(x)
        qk, v = tuple(rearrange(qkv, 'b t (d k h) -> k b h t d', k=2, h=self.num_heads))
        q = k = qk

        # Enforcing Lipschitzness of Transformer
        # Due to Lipschitz constant of standard dot product self-attention layer can be unbounded,
        # So adopt the L2 attention replace the dot product.
        score = -((torch.einsum('... t d,... t d -> ... t', q, q)).unsqueeze(3) +
                  (torch.einsum('... s d,... s d -> ... s', k, k)).unsqueeze(2) -
                  2 * torch.einsum('... t d, ... s d -> ... t s', q, k))

        attn = score * self.scale
        attn = torch.softmax(attn, dim=-1)
        attn = self.attn_drop(attn)

        x = torch.einsum("... t s, ... s d -> ... t d", attn, v)
        x = rearrange(x, "b h t d -> b t (h d)")
        x = self.proj(x)
        x = self.proj_drop(x)
        return x

