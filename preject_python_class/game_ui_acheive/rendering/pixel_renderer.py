"""Procedural pixel art, perspective road and short-lived particles."""
import math
import random
import pygame

class PixelRenderer:
    def __init__(self,size=(320,180)):
        self.base=pygame.Surface(size)
        self.rng=random.Random()
        self.reset()

    def reset(self):
        self.distance=0.
        self.t=0.
        self.effect_time=0.
        self.dust_t=0.
        self.particles=[]

    def player_x(self,p):
        return self.lane_x(p.position,.94)

    def lane_x(self,lane,z):
        return int(160+lane*(14+z*34))

    def advance(self,dt,speed,player,dash=False):
        self.distance+=speed*dt/900
        self.t+=dt
        self.dust_t-=dt
        if self.dust_t<=0 and player.jump<2:
            self.burst(self.player_x(player),165,(110,210,255) if dash else (179,143,98),3 if dash else 1)
            self.dust_t=.035 if dash else .1

    def update_effects(self,dt):
        self.effect_time+=dt
        for p in self.particles:
            p[0]+=p[2]*dt
            p[1]+=p[3]*dt
            p[3]+=55*dt
            p[4]-=dt
        self.particles=[p for p in self.particles if p[4]>0]

    def begin(self):
        s=self.base
        s.fill((99,182,222))
        pygame.draw.circle(s,(255,230,151),(249,24),12)
        for x in (27,113,207):
            pygame.draw.rect(s,(204,231,235),(x,20,30,5))
            pygame.draw.rect(s,(204,231,235),(x+6,15,16,5))
        pygame.draw.rect(s,(57,132,75),(0,59,320,121))
        pygame.draw.polygon(s,(37,102,66),[(0,65),(110,62),(0,180)])
        pygame.draw.polygon(s,(42,114,67),[(210,62),(320,65),(320,180)])
        for x in (8,267):
            pygame.draw.polygon(s,(83,63,54),[(x+43,36),(x+49,32),(x+49,60),(x+43,64)])
            pygame.draw.rect(s,(132,91,67),(x,36,43,28))
            pygame.draw.polygon(s,(87,54,50),[(x-3,36),(x+20,24),(x+46,36)])
            for dx in (7,26):
                pygame.draw.rect(s,(51,62,71),(x+dx,43,9,11))
        pygame.draw.polygon(s,(105,77,58),[(110,62),(210,62),(320,180),(0,180)])
        pygame.draw.line(s,(233,198,131),(110,62),(0,180),2)
        pygame.draw.line(s,(233,198,131),(210,62),(320,180),2)
        for i in range(12):
            z=(i/12+self.distance)%1.18
            y=int(62+100*z)
            width=int(50+93*z)
            pygame.draw.line(s,(83,61,48),(160-width,y),(160+width,y),max(1,int(z*2)))
        for lane in (-.5,.5):
            for i in range(8):
                z=(i/8+self.distance)%1.18
                a=(self.lane_x(lane,z),int(65+100*z))
                b=(self.lane_x(lane,z+.05),int(65+100*(z+.05)))
                pygame.draw.line(s,(224,197,142),a,b,max(1,int(1+z)))
        for x in (22,286):
            pygame.draw.rect(s,(82,69,43),(x+4,57,5,16))
            pygame.draw.rect(s,(28,92,51),(x-3,45,19,15))
            pygame.draw.rect(s,(45,119,57),(x,39,13,12))

    def draw_world(self,obs,coins,player):
        # Far objects first, allowing nearer objects to cover them.
        for obj in sorted([*obs,*coins],key=lambda o:o.z):
            if hasattr(obj,"kind"):
                self.draw_obstacle(obj)
            else:
                self.draw_coin(obj)

    def draw_obstacle(self,o):
        s=self.base
        x=self.lane_x(o.lane,o.z)
        y=int(65+o.z*100)
        k=.4+o.z
        w=max(4,int(14*k))
        h=max(8,int(27*k))
        depth=max(3,int(6*k))
        if o.kind != "gap":
            pygame.draw.ellipse(s,(66,53,43),(x-w-2,y-3,2*w+depth+10,8))
            pygame.draw.polygon(s,(63,64,65),[(x+w,y-h),(x+w+depth,y-h-depth),(x+w+depth,y-depth),(x+w,y)])
            pygame.draw.polygon(s,(165,165,142),[(x-w,y-h),(x-w+depth,y-h-depth),(x+w+depth,y-h-depth),(x+w,y-h)])
        if o.kind=="wall":
            pygame.draw.rect(s,(188,60,46),(x-w,y-h,2*w,h))
            pygame.draw.rect(s,(239,159,102),(x-w,y-h,2*w,3))
            for row in range(1,4):
                yy=y-h+row*h//4
                pygame.draw.line(s,(114,47,41),(x-w,yy),(x+w-1,yy))
                xx=x+(w//2 if row%2 else -w//2)
                pygame.draw.line(s,(114,47,41),(xx,yy),(xx,min(y,yy+h//4)))
        elif o.kind=="gap":
            depth=max(4,int(12*k))
            pygame.draw.polygon(s,(24,27,34),[(x-w,y-depth),(x+w,y-depth),(x+w+5,y+3),(x-w-5,y+3)])
            pygame.draw.line(s,(229,174,63),(x-w,y-depth),(x+w,y-depth),2)
            pygame.draw.polygon(s,(80,51,41),[(x-w,y-depth),(x+w,y-depth),(x+w-4,y-depth+6),(x-w+4,y-depth+6)])
            pygame.draw.line(s,(61,44,43),(x-w+3,y-depth+3),(x+w-3,y-depth+3),2)
        elif o.kind=="tunnel":
            pygame.draw.rect(s,(62,80,86),(x-w-3,y-h-7,2*w+6,h+7))
            pygame.draw.rect(s,(23,38,46),(x-w+4,y-h+7,max(2,2*w-8),h-7))
            pygame.draw.rect(s,(116,153,143),(x-w-3,y-h-7,2*w+6,6))
            for dx in range(-w,w,7):
                pygame.draw.rect(s,(229,189,61),(x+dx,y-h,4,5))
        else:
            pygame.draw.rect(s,(117,132,134),(x-w,y-h,3,h))
            pygame.draw.rect(s,(117,132,134),(x+w-3,y-h,3,h))
            pygame.draw.rect(s,(239,183,47),(x-w-3,y-h-4,2*w+6,max(6,int(12*k))))
            pygame.draw.line(s,(73,65,39),(x-5,y-h),(x,y-h+5),2)
            pygame.draw.line(s,(73,65,39),(x,y-h+5),(x+5,y-h),2)

    def draw_coin(self,c):
        if c.z < 0: return
        x=self.lane_x(c.lane,c.z)
        y=int(65+c.z*100)
        r=max(2,int(5*(.5+c.z)))
        width=max(1,int(r*abs(math.cos(c.phase))))
        pygame.draw.ellipse(self.base,(255,198,35),(x-width,y-r,2*width,2*r))
        pygame.draw.line(self.base,(255,241,135),(x,y-r+1),(x,y+r-1))

    def draw_player(self,p,shield=False,dash=False,hit=False):
        s=self.base
        x=self.player_x(p)
        pygame.draw.ellipse(s,(47,43,41),(x-11,162,22,5))
        feet=164-int(p.jump)
        stride=math.sin(p.phase)*5*(1-p.crouch_amount) if p.jump<1 else 0
        body=pygame.Surface((44,54),pygame.SRCALPHA)
        # Facing away: cap, head, shirt, overalls and swinging limbs.
        pygame.draw.rect(body,(228,48,41),(12,2,20,5))
        pygame.draw.rect(body,(180,37,34),(14,0,16,5))
        pygame.draw.rect(body,(255,188,125),(15,7,14,10))
        pygame.draw.rect(body,(98,57,42),(15,7,14,3))
        pygame.draw.rect(body,(223,50,40),(13,17,18,17))
        pygame.draw.rect(body,(44,81,159),(16,27,12,13))
        arm=int(stride)
        for side in (-1,1):
            ax=22+side*13
            ay=22+side*arm
            if p.jump>1:
                ay=14
            pygame.draw.line(body,(221,48,38),(22+side*8,20),(ax,ay+9),5)
            pygame.draw.rect(body,(255,188,125),(ax-2,ay+8,4,4))
            legx=22+side*5
            legy=47+int(side*stride)
            pygame.draw.line(body,(36,67,141),(legx,35),(legx+int(side*stride*.3),legy),5)
            pygame.draw.rect(body,(44,39,48),(legx-3,legy,7,3))
        pygame.draw.rect(body,(255,105,69),(13,17,3,15))
        pygame.draw.rect(body,(149,38,39),(28,19,3,15))
        pygame.draw.rect(body,(76,125,204),(16,28,3,11))
        pygame.draw.rect(body,(26,49,103),(25,29,3,11))
        pygame.draw.rect(body,(255,216,163),(15,10,3,6))
        pygame.draw.rect(body,(202,129,92),(26,10,3,6))
        height=int(54*(1-.42*p.crouch_amount))
        if p.crouch_amount:
            body=pygame.transform.scale(body,(44,height))
        if dash:
            for offset in (9,17,25):
                pygame.draw.line(s,(117,211,251),(x-22-offset,feet-height//2),(x-15-offset,feet-height//2-3),2)
        if not hit or int(self.effect_time*20)%2==0:
            s.blit(body,(x-22,feet-height))
        if shield:
            pygame.draw.ellipse(s,(96,231,246),(x-24,feet-height-4,48,height+8),2)

    def burst(self,x,y,color,n):
        for _ in range(n):
            self.particles.append([float(x),float(y),self.rng.uniform(-40,40),
                                   self.rng.uniform(-50,5),self.rng.uniform(.2,.55),color])
        self.particles=self.particles[-240:]

    def draw_effects(self):
        for x,y,_,_,life,color in self.particles:
            pygame.draw.rect(self.base,color,(int(x),int(y),2 if life>.2 else 1,2 if life>.2 else 1))

    def present(self,target):
        pygame.transform.scale(self.base,target.get_size(),target)

