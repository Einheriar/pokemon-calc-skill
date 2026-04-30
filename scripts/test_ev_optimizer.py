#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Quick test for EV optimizer (Phase 3)."""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from models import Pokemon, Move, Field
from ev_optimizer import optimize_evs

# Attacker: Charizard Lv50, Modest, 0 SA EVs initially
att = Pokemon(
    name='喷火龙', name_en='Charizard', level=50,
    base_stats={'hp':78,'attack':84,'defense':78,'sp_attack':109,'sp_defense':85,'speed':100},
    evs={'hp':0,'attack':0,'defense':0,'sp_attack':0,'sp_defense':0,'speed':0},
    ivs={'hp':31,'attack':31,'defense':31,'sp_attack':31,'sp_defense':31,'speed':31},
    nature='内敛', ability='Blaze', item='木炭',
    types=['火','飞行'],
)

# Defender: Blastoise Lv50, Calm, 252 HP/SD
# current_hp will be computed from base stats
# Let's set it manually for the test, but compute_raw_stats needs to run
dfn = Pokemon(
    name='水箭龟', name_en='Blastoise', level=50,
    base_stats={'hp':79,'attack':83,'defense':100,'sp_attack':85,'sp_defense':105,'speed':78},
    evs={'hp':252,'attack':0,'defense':0,'sp_attack':0,'sp_defense':252,'speed':4},
    ivs={'hp':31,'attack':31,'defense':31,'sp_attack':31,'sp_defense':31,'speed':31},
    nature='温和', ability='Torrent', item='',
    types=['水'],
)

move = Move(name='Flamethrower', name_zh='喷射火焰', base_power=90, type='火', category='Special')
field = Field()

print("=" * 60)
print("Test 1: Optimize Attack EV for OHKO")
print("=" * 60)
result = optimize_evs(att, dfn, move, field, goal="ko", target="ohko")
print("Success:", result.get("success"))
print("Optimal EV:", result.get("optimal_ev"))
print("Remaining EVs:", result.get("remaining_evs"))
print("Damage range:", result.get("damage_range"))
print()

print("=" * 60)
print("Test 2: Optimize Defense EV to survive")
print("=" * 60)
result2 = optimize_evs(att, dfn, move, field, goal="survive", target="survive")
print("Success:", result2.get("success"))
print("Optimal EV:", result2.get("optimal_ev"))
print("Stat:", result2.get("stat"))
print("Damage range:", result2.get("damage_range"))
print()

print("=" * 60)
print("Test 3: Optimize HP + Defense bulk")
print("=" * 60)
result3 = optimize_evs(att, dfn, move, field, goal="survive_bulk", target="survive")
print("Success:", result3.get("success"))
print("HP EV:", result3.get("optimal_hp_ev"))
print("Def EV:", result3.get("optimal_def_ev"))
print("Total EVs:", result3.get("total_evs"))
print("Remaining EVs:", result3.get("remaining_evs"))
print("Damage range:", result3.get("damage_range"))
