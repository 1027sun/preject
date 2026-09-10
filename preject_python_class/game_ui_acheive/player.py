"""Continuous runner movement in lane units and pixel-height units."""
import math

class Player:
    def __init__(self):
        self.lane = 0
        self.position = 0.
        self.jump = 0.
        self.jump_time = 0.
        self.crouch = False
        self.crouch_amount = 0.
        self.phase = 0.
        self.jump_buffer = 0.

    def apply(self, state, dt):
        self.lane = state.lane
        self.position += (self.lane-self.position)*(1-math.exp(-18*dt))
        self.crouch = state.crouch
        self.crouch_amount += (float(self.crouch)-self.crouch_amount)*(1-math.exp(-22*dt))
        self.phase += dt*12
        self.jump_buffer = .12 if state.jump_triggered else max(0.,self.jump_buffer-dt)
        started = bool(self.jump_buffer > 0 and self.jump_time <= 0 and not self.crouch)
        if started:
            self.jump_time = .8
            self.jump_buffer = 0.
        if self.jump_time > 0:
            self.jump_time = max(0., self.jump_time-dt)
            progress = 1-self.jump_time/.8
            self.jump = 42*4*progress*(1-progress)
        else:
            self.jump = 0.
        return started

