"""Original synthesized chiptune and effects; no external audio assets."""
import math
from array import array
import pygame

class Audio:
    def __init__(self):
        self.enabled = False
        self.running = False
        self.channel = None
        self.sounds = {}
        self.music_volume = .6
        self.effects_volume = .8
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init(22050,-16,1)
            self.rate, _, self.channels = pygame.mixer.get_init()
            pygame.mixer.set_reserved(1)
            self.channel = pygame.mixer.Channel(0)
            self.sounds = {
                "jump":self.sequence([330,440,660],.055,.22),
                "coin":self.sequence([880,1320],.065,.18),
                "skill":self.sequence([262,392,523,784],.06,.22),
                "hit":self.sequence([160,110,70,40],.08,.3)}
            self.music = self.sequence([262,330,392,330,294,349,440,349,
                                       330,392,494,392,294,349,392,196],.18,.065)
            self.channel.play(self.music,loops=-1)
            self.set_volumes(self.music_volume,self.effects_volume)
            self.channel.unpause()
            self.enabled = True
        except (pygame.error,ValueError):
            self.channel = None

    def set_volumes(self,music,effects):
        self.music_volume=max(0.,min(1.,music)); self.effects_volume=max(0.,min(1.,effects))
        if self.channel: self.channel.set_volume(self.music_volume)
        for sound in self.sounds.values(): sound.set_volume(self.effects_volume)

    def sequence(self,notes,duration,volume):
        samples=array("h")
        count=int(self.rate*duration)
        for freq in notes:
            for i in range(count):
                t=i/self.rate
                env=min(1.,i/(self.rate*.008))*min(1.,(count-i)/(self.rate*.025))
                wave=math.sin(2*math.pi*freq*t)+.2*math.sin(6*math.pi*freq*t)
                value=int(32767*volume*env*wave/1.2)
                samples.extend([value]*self.channels)
        return pygame.mixer.Sound(buffer=samples.tobytes())

    def set_running(self,running):
        self.running=running
        if self.channel:
            if self.enabled and running:
                self.channel.unpause()
            else:
                self.channel.pause()

    def play(self,name):
        if self.enabled and name in self.sounds:
            self.sounds[name].play()

    def toggle(self):
        self.enabled=not self.enabled if self.channel else False
        if not self.enabled:
            for sound in self.sounds.values():
                sound.stop()
        self.set_running(self.running)

    def close(self):
        if pygame.mixer.get_init():
            pygame.mixer.stop()

