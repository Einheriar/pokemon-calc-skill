#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Quick test for damage calculation engine."""
import sys
import os

# Add scripts dir to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from models import Pokemon, Move, Field
from damage import calculate_damage

# Attacker: Charizard Lv50, Modest, 252 SA, Charcoal
att = Pokemon(
    name='喷火龙', name_en='Charizard', level=50,
    base_stats={'hp':78,'attack':84,'defense':78,'sp_attack':109,'sp_defense':85,'speed':100},
    evs={'hp':4,'attack':0,'defense':0,'sp_attack':252,'sp_defense':0,'speed':252},
    ivs={'hp':31,'attack':31,'defense':31,'sp_attack':31,'sp_defense':31,'speed':31},
    nature='内敛', ability='Blaze', item='木炭',
    types=['火','飞行'],
)

# Defender: Blastoise Lv50, Calm, 252 SD
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

result = calculate_damage(att, dfn, move, field, gen=9)
print('Description:', result.description)
print('Damage rolls:', result.damage)
print('Min:', result.min_damage, 'Max:', result.max_damage)
print('Crit:', result.is_critical, 'STAB:', result.stab_applied, 'Burn:', result.burn_applied)
