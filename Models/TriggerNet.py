import torch
import torch.nn as nn      
class DoubleConv(nn.Module):
    def __init__(self, in_channels, out_channels, mid_channels=None):
        super().__init__()
        if not mid_channels:
            mid_channels = out_channels
        self.double_conv = nn.Sequential(
            nn.Conv3d(in_channels, mid_channels, kernel_size=3, padding=1),
            nn.BatchNorm3d(mid_channels),
            nn.LeakyReLU(negative_slope=0.01 , inplace=True),
            
            nn.Conv3d(mid_channels, out_channels, kernel_size=3, padding=1),
            nn.BatchNorm3d(out_channels),
            nn.LeakyReLU(negative_slope=0.01 , inplace=True),
        )

    def forward(self, x):
        return self.double_conv(x)
    
    
class Conv_11(nn.Module):
    def __init__(self, in_channels, out_channels, mid_channels=None):
        super().__init__()
        if not mid_channels:
            mid_channels = out_channels
        self.conv = nn.Sequential(
            nn.Conv3d(in_channels, out_channels, kernel_size=1),
            nn.BatchNorm3d(mid_channels),
            nn.LeakyReLU(negative_slope=0.01 , inplace=True),
        )

    def forward(self, x1,x2):
        x = torch.cat([x2, x1], dim=1)
        return self.conv(x)
    

class DoubleConv_s2(nn.Module):
    def __init__(self, in_channels, out_channels,reduce_depth):
        super().__init__()
        
        if reduce_depth:
            stride = (2,2,2)
        else:
            stride = (1,2,2)

        self.double_conv = nn.Sequential(
            nn.Conv3d(in_channels, out_channels, kernel_size=3, padding=1,stride=stride),
            nn.BatchNorm3d(out_channels),
            nn.LeakyReLU(negative_slope=0.01 , inplace=True),
            
            nn.Conv3d(out_channels, out_channels, kernel_size=3, padding=1),
            nn.BatchNorm3d(out_channels),
            nn.LeakyReLU(negative_slope=0.01 , inplace=True),
        )

    def forward(self, x):
        return self.double_conv(x)
    
    
class Down(nn.Module):
    def __init__(self, in_channels, out_channels,reduce_depth= False):
        super().__init__()
        self.conv_s2 = nn.Sequential(
            DoubleConv_s2(in_channels, out_channels,reduce_depth)
        )

    def forward(self, x):
        return self.conv_s2(x)

class Up(nn.Module):
    def __init__(self, in_channels, out_channels, reduce_depth= False,increase_channels = True):
        super().__init__()
        
        print('in_channels-->',in_channels)
        print('out_channels-->',out_channels)
        print('%%% ->',in_channels%out_channels)
        if increase_channels:
            if (in_channels%out_channels) ==0:
                mid_channel = in_channels
            else:
                mid_channel = in_channels + 96  
        else:
            mid_channel = in_channels + in_channels//2
            
        print('mid_channel -->',mid_channel)

        if reduce_depth :
            self.up = nn.ConvTranspose3d(in_channels, in_channels // 2 , kernel_size=(2,2,2), stride=(2,2,2))
        else:
            self.up = nn.ConvTranspose3d(in_channels, in_channels // 2, kernel_size=(1,2,2), stride=(1,2,2))
        self.conv = DoubleConv(mid_channel, out_channels)

    def forward(self, x1, x2):
        x1 = self.up(x1)
        
        print(x1.shape)
        print(x2.shape)
        x = torch.cat([x2, x1], dim=1)
        return self.conv(x)
    
class OutConv(nn.Module):
    def __init__(self, in_channels, out_channels):
        super(OutConv, self).__init__()
        self.conv = nn.Conv3d(in_channels, out_channels, kernel_size=1)

    def forward(self, x):
        return self.conv(x)

Base = 32
class BaseLine1(nn.Module):
    def __init__(self, n_channels = 1):
        super(BaseLine1, self).__init__()
        self.n_channels = n_channels

        self.inc = DoubleConv(n_channels, Base) 
        self.down1 = Down(Base, 2*Base,True) # reduce_depth
        self.down2 = Down(2*Base, 4*Base,True) # reduce_depth
        self.down3 = Down(4*Base, 8*Base,True) # reduce_depth
        self.down4 = Down(8*Base, 10*Base,True) # reduce_depth
        self.down5 = Down(10*Base, 10*Base) # reduce_depth 
        
        self.up0 = Up(10*Base, 10*Base,False,False)
        self.up1 = Up(10*Base, 8*Base,True,True)
        self.up2 = Up(8*Base, 4*Base,True,True)
        self.up3 = Up(4*Base, 2*Base,True,True)
        self.up4 = Up(2*Base, Base,True,True)

        self.outc = OutConv(Base,4)
        
        self.dropout6E = nn.Dropout2d(p=0.30) 
        
    def forward(self, x):

        x1 = self.inc(x)
        x2 = self.down1(x1)
        x3 = self.down2(x2)
        x4 = self.down3(x3)
        x5 = self.down4(x4) 
        x6 = self.down5(x5) 
        x6 = self.dropout6E(x6)

        z1 = self.up0(x6, x5)
        z2 = self.up1(z1, x4)
        z3 = self.up2(z2, x3)
        z4 = self.up3(z3, x2)
        z5 = self.up4(z4, x1)
        logits1 = self.outc(z5)

        return logits1
    
# Input_Image_Channels = 1
# def model() -> BaseLine1:
#     model = BaseLine1()
#     return model
# DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
# from torchsummary import summary
# model = model()
# model.to(device=DEVICE,dtype=torch.float)
# summary(model, [(Input_Image_Channels, 64,96,96)])

from ptflops import get_model_complexity_info
net = BaseLine1()
flops, params = get_model_complexity_info(net, (1,64,192,192), as_strings=True,
                                            print_per_layer_stat=True, verbose=True)
print('{:<30}  {:<8}'.format('Computational complexity: ', flops))
print('{:<30}  {:<8}'.format('Number of parameters: ', params))
