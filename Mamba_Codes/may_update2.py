from torch import nn
from timm.models.layers import to_2tuple
import torch
from einops import rearrange
import math


DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

embed_dim = 96
img_size = 160
patch_size = 4

class PatchEmbed(nn.Module): # [2,1,160,160] -->[2,1600,96]
    def __init__(self, img_size=160, patch_size=patch_size, in_chans=1, embed_dim=embed_dim, norm_layer=None):
        super().__init__()
        img_size = to_2tuple(img_size)
        patch_size = to_2tuple(patch_size)
        patches_resolution = [img_size[0] //
                              patch_size[0], img_size[1] // patch_size[1]]
        self.img_size = img_size
        self.patch_size = patch_size
        self.patches_resolution = patches_resolution
        self.num_patches = patches_resolution[0] * patches_resolution[1]

        self.in_chans = in_chans
        self.embed_dim = embed_dim

        self.proj = nn.Conv2d(in_chans, embed_dim,
                              kernel_size=patch_size, stride=patch_size)
        if norm_layer is not None:
            self.norm = norm_layer(embed_dim)
        else:
            self.norm = None

    def forward(self, x):
        B, C, H, W = x.shape
        # FIXME look at relaxing size constraints
        assert H == self.img_size[0] and W == self.img_size[1], \
            f"Input image size ({H}*{W}) doesn't match model ({self.img_size[0]}*{self.img_size[1]})."
        x = self.proj(x).flatten(2).transpose(1, 2)  # B Ph*Pw C
        if self.norm is not None:
            x = self.norm(x)
        return x
    
    
# patch_embd = PatchEmbed()
# img = torch.randn(2,1,160,160)
# y = patch_embd(img)

class PatchMerging(nn.Module):  # [2,1600,96] -->[2,400,192]
    r""" Patch Merging Layer.

    Args:
        input_resolution (tuple[int]): Resolution of input feature.
        dim (int): Number of input channels.
        norm_layer (nn.Module, optional): Normalization layer.  Default: nn.LayerNorm
    """

    def __init__(self, input_resolution, dim, norm_layer=nn.LayerNorm):
        super().__init__()
        self.input_resolution = input_resolution
        self.dim = dim
        self.reduction = nn.Linear(4 * dim, 2 * dim, bias=False)
        self.norm = norm_layer(4 * dim)

    def forward(self, x):
        """
        x: B, H*W, C
        """
        H, W = self.input_resolution
        B, L, C = x.shape
        assert L == H * W, "input feature has wrong size"
        assert H % 2 == 0 and W % 2 == 0, f"x size ({H}*{W}) are not even."

        x = x.view(B, H, W, C)

        x0 = x[:, 0::2, 0::2, :]  # B H/2 W/2 C
        x1 = x[:, 1::2, 0::2, :]  # B H/2 W/2 C
        x2 = x[:, 0::2, 1::2, :]  # B H/2 W/2 C
        x3 = x[:, 1::2, 1::2, :]  # B H/2 W/2 C
        x = torch.cat([x0, x1, x2, x3], -1)  # B H/2 W/2 4*C
        x = x.view(B, -1, 4 * C)  # B H/2*W/2 4*C

        x = self.norm(x)
        x = self.reduction(x)

        return x

    def extra_repr(self) -> str:
        return f"input_resolution={self.input_resolution}, dim={self.dim}"

    def flops(self):
        H, W = self.input_resolution
        flops = H * W * self.dim
        flops += (H // 2) * (W // 2) * 4 * self.dim * 2 * self.dim
        return flops

# p_expand = PatchMerging([40,40],96)
# y1 = p_expand(y)

class PatchExpand(nn.Module):
    def __init__(self, input_resolution, dim, dim_scale=2, norm_layer=nn.LayerNorm):
        super().__init__()
        self.input_resolution = input_resolution
        self.dim = dim
        self.expand = nn.Linear(dim, 4*dim, bias=False) if dim_scale==2 else nn.Identity()
        self.norm = norm_layer(dim)

    def forward(self, x):
        
        """
        x: B, H*W, C
        """
        print(self.input_resolution)
        H, W = self.input_resolution
        x = self.expand(x)
        #print(x.shape)
        B, L, C = x.shape
        assert L == H * W, "input feature has wrong size"

        x = x.view(B, H, W, C)
        x = rearrange(x, 'b h w (p1 p2 c)-> b (h p1) (w p2) c', p1=2, p2=2, c=C//4)
        x = x.view(B,-1,C//4)
        x= self.norm(x)

        return x


class Down(nn.Module):
    def __init__(self, size, dim):
        super().__init__()
        self.down_1 = nn.Sequential(
            PatchMerging([size,size],dim)
        )
    def forward(self, x):
        return self.down_1(x)
    

class Up(nn.Module):
    def __init__(self, size, dim):
        super().__init__()
        self.up_1 = nn.Sequential(
            nn.Linear(dim, dim//2, bias=False),
            PatchExpand([size,size],dim//2)
        )
    def forward(self, x):
        return self.up_1(x)
    
    
class UNet(nn.Module):
    def __init__(self, n_channels=1):
        super(UNet, self).__init__()
        self.n_channels = n_channels

        self.inc = PatchEmbed()
        
        self.down1 = Down(img_size//patch_size,embed_dim)
        self.down2 = Down(img_size//(patch_size*2),embed_dim*2)
        self.down3 = Down(img_size//(patch_size*4),embed_dim*4)
        
        
        
        self.up1 = Up(img_size//(patch_size*8),embed_dim*8)
        self.up2 = Up(img_size//(patch_size*4),embed_dim*4)
        self.up3 = Up(img_size//(patch_size*2),embed_dim*2)
        self.up4 = Up(img_size//(patch_size),embed_dim)
        self.up5 = Up(img_size//(patch_size//2),embed_dim//2)
       
        
        #self.pos_embed =  positionalencoding2d(64,160,160).to(DEVICE)
        self.output = nn.Conv2d(24, 5, kernel_size=1, bias=False)
        

    def forward(self, inp):
        
        #print(inp.shape)
        
        x = self.inc(inp)
        #print(x.shape)
        x1 = self.down1(x)
        #print(x1.shape)
        x2 = self.down2(x1)
        #print(x2.shape)
        
        x3 = self.down3(x2)
        print(x3.shape)
        
        y1 = self.up1(x3)
        print(y1.shape)
        
        y2 = self.up2(y1)
        print(y2.shape)
        
        y3 = self.up3(y2)
        print(y3.shape)
        
        y4 = self.up4(y3)
        print(y4.shape)
        
        y5 = self.up5(y4)
        print(y5.shape)
        
        B, L, C = y5.shape
        H = W = int(math.sqrt(L))
        y5 = y5.view(B, H, W, C)
        
        y5 = y5.permute(0, 3, 1, 2).contiguous()
        
        print(y5.shape)
        
        y5 = self.output(y5)
        
        return y5
        
        

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
def model() -> UNet:
    model = UNet()
    model.to(device=DEVICE,dtype=torch.float)
    return model
from torchsummary import summary
model = model()
summary(model, [(1, 160,160)])
#
#model = UNet()
#num_parameters = sum(p.numel() for p in model.parameters() if p.requires_grad)
#print("Number of trainable parameters:", num_parameters)


