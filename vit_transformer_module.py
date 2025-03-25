import torch
import torchvision

from torch import nn
from torchvision import transforms


class PatchEmbedding(nn.Module):
'''Turns a 2D input image into a 1D sequence learnable embedding vector.'''

    def __init__(
        self,
        in_channels: int=3,
        patch_size: int=16,
        embedding_dim: int=768):

        super().__init__()

        # Ensure input image is divisible by patch size
        self.patch_size = patch_size

        # Create the patch embedding layer (convolution)
        self.patcher = nn.Conv2d(
        in_channels=in_channels,
        out_channels=embedding_dim,
        kernel_size=patch_size,
        stride=patch_size,
        padding=0)

        # Flatten the patch feature maps into a single dimension
        self.flatten = nn.Flatten(start_dim=2, end_dim=3)

    def forward(self, x):
        # Ensure image size is divisible by patch size
        image_resolution = x.shape[-1]
        assert image_resolution % self.patch_size == 0, \
        f'Input image size must be divisible by patch size, \
        image shape: {image_resolution}, \
        patch size: {self.patch_size}'

        # Apply patch embedding
        x_patched = self.patcher(x)
        x_flattened = self.flatten(x_patched)

        # Return flattened and permuted output
        return x_flattened.permute(0, 2, 1)  # [batch_size, N, P^2*C]




class MultiheadSelfAttentionBlock(nn.Module):
    '''Creates a multi-head self-attention block (MSA block).'''
    
    def __init__(
        self,
        embedding_dim: int=768,
        num_heads: int=12,
        attn_dropout: float=0):
        
        super().__init__()
        
        # Layer Normalization
        self.layer_norm = nn.LayerNorm(normalized_shape=embedding_dim)
        
        # Multi-Head Attention layer
        self.multihead_attn = nn.MultiheadAttention(
            embed_dim=embedding_dim,
            num_heads=num_heads,
            dropout=attn_dropout,
            batch_first=True)  # Ensure batch dimension is first
        
    def forward(self, x):
        # Apply LayerNorm and multi-head attention
        x = self.layer_norm(x)
        attn_output, _ = self.multihead_attn(
            query=x,
            key=x,
            value=x,
            need_weights=False)
        
        return attn_output




class MLPBlock(nn.Module):
    '''Creates a multi-layer perceptron block (MLP block).'''
    
    def __init__(
        self,
        embedding_dim: int=768,
        mlp_size: int=3072,
        dropout: float=0.1):
        
        super().__init__()
        
        # Layer Normalization
        self.layer_norm = nn.LayerNorm(normalized_shape=embedding_dim)
        
        # MLP layers
        self.mlp = nn.Sequential(
            nn.Linear(in_features=embedding_dim, out_features=mlp_size),
            nn.GELU(),
            nn.Dropout(p=dropout),
            nn.Linear(in_features=mlp_size, out_features=embedding_dim),
            nn.Dropout(p=dropout)
        )
    
    def forward(self, x):
        # Apply LayerNorm and MLP
        x = self.layer_norm(x)
        x = self.mlp(x)
        
        return x




class TransformerEncoderBlock(nn.Module):
'''Creates a Transformer Encoder block.'''

    def __init__(
        self,
        embedding_dim: int=768,
        num_heads: int=12,
        mlp_size: int=3072, 
        mlp_dropout: float=0.1,
        attn_dropout: float=0):

        super().__init__()

        # MSA and MLP blocks
        self.msa_block = MultiheadSelfAttentionBlock(
        embedding_dim=embedding_dim, 
        num_heads=num_heads, 
        attn_dropout=attn_dropout)

        self.mlp_block = MLPBlock(
        embedding_dim=embedding_dim,
        mlp_size=mlp_size,
        dropout=mlp_dropout)

    def forward(self, x):
        # Residual connections
        x = self.msa_block(x) + x
        x = self.mlp_block(x) + x
    
        return x




class ViT(nn.Module):
'''Creates a Vision Transformer architecture.'''

    def __init__(
        self,
        img_size: int=224, in_channels: int=3,
        patch_size: int=16, 
        num_transformer_layers: int=12,
        embedding_dim: int=768, mlp_size: int=3072, 
        num_heads: int=12,
        attn_dropout: float=0,
        mlp_dropout: float=0.1, 
        embedding_dropout: float=0.1,
        num_classes: int=1000):

        super().__init__()

        # Ensure image size is divisible by patch size
        assert img_size % patch_size == 0, \
        f'Image size must be divisible by patch size, \
        image size: {img_size}, patch size: {patch_size}.'

        # Number of patches
        self.num_patches = (img_size * img_size) // patch_size**2

        # Learnable embeddings
        self.class_embedding = nn.Parameter(
        torch.randn(1, 1, embedding_dim),
        requires_grad=True)
        self.position_embedding = nn.Parameter(
        torch.randn(1, self.num_patches + 1,
        embedding_dim),
        requires_grad=True)
        self.embedding_dropout = nn.Dropout(p=embedding_dropout)

        # Patch embedding layer
        self.patch_embedding = PatchEmbedding(
        in_channels=in_channels,
        patch_size=patch_size,
        embedding_dim=embedding_dim)

        # Transformer Encoder blocks
        self.transformer_encoder = nn.Sequential(
        *[TransformerEncoderBlock(
            embedding_dim=embedding_dim,
            num_heads=num_heads,
            mlp_size=mlp_size,
            mlp_dropout=mlp_dropout,
            attn_dropout=attn_dropout) 
          for _ in range(num_transformer_layers)])

        # Classifier head
        self.classifier = nn.Sequential(
        nn.LayerNorm(normalized_shape=embedding_dim),
        nn.Linear(
            in_features=embedding_dim,
            out_features=num_classes)
        )

    def forward(self, x):
        # Create class token and expand it to batch size
        batch_size = x.shape[0]
        class_token = self.class_embedding.expand(batch_size, -1, -1)

        # Get patch embedding
        x = self.patch_embedding(x)

        # Concatenate class token with patch embeddings
        x = torch.cat((class_token, x), dim=1)

        # Add position embedding
        x = self.position_embedding + x

        # Apply embedding dropout
        x = self.embedding_dropout(x)

        # Pass through transformer encoder
        x = self.transformer_encoder(x)

        # Use class token (index 0) for classification
        x = self.classifier(x[:, 0])  # [batch_size, num_classes]

        return x