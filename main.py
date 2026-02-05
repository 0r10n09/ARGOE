#!/usr/bin/env python3

import os
import time
import sys
import random
import json
from pathlib import Path
from dataclasses import dataclass
from enum import IntEnum
from typing import List, Tuple, Optional, Dict
from abc import ABC, abstractmethod


class Opcode(IntEnum):
    """CPU Instruction opcodes"""
    NOP = 0x00
    LDA_IMM = 0x01
    STA_ABS = 0x02
    ADD = 0x03
    LDB_IMM = 0x04
    CMP = 0x05
    JMP = 0x06
    JZ = 0x07
    INP = 0x08
    SUB = 0x09
    LDC_IMM = 0x0A
    LDD_IMM = 0x0B
    INC = 0x0C
    DEC = 0x0D
    JNZ = 0x0E
    LDA_ABS = 0x10
    LDA_IDX = 0x11
    STA_IDX = 0x12
    CALL = 0x13
    RET = 0x14
    MOV_BA = 0x16
    MOV_AB = 0x17
    MOV_CA = 0x18
    MOV_AC = 0x19
    MOV_DA = 0x1A
    MOV_AD = 0x1B
    AND = 0x20
    OR = 0x21
    HALT = 0xFF


class DisplayChar(IntEnum):
    """Display character codes"""
    EMPTY = 0
    LIGHT = 1
    MEDIUM = 2
    HEAVY = 3
    WALL = 4
    FOOD = 5
    PADDLE = 6
    BALL = 7
    SNAKE_BODY = 8
    SNAKE_HEAD = 9
    BRICK = 10
    CAR = 11
    OBSTACLE = 12
    AI_CAR = 13
    FINISH = 14
    PACMAN = 15


class Style:
    """ANSI color and effect codes"""
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    ITALIC = "\033[3m"
    BLINK = "\033[5m"
    REVERSE = "\033[7m"

    BLACK = "\033[30m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    WHITE = "\033[37m"

    BRIGHT_BLACK = "\033[90m"
    BRIGHT_RED = "\033[91m"
    BRIGHT_GREEN = "\033[92m"
    BRIGHT_YELLOW = "\033[93m"
    BRIGHT_BLUE = "\033[94m"
    BRIGHT_MAGENTA = "\033[95m"
    BRIGHT_CYAN = "\033[96m"
    BRIGHT_WHITE = "\033[97m"

    BG_BLACK = "\033[40m"
    BG_RED = "\033[41m"
    BG_GREEN = "\033[42m"
    BG_YELLOW = "\033[43m"
    BG_BLUE = "\033[44m"
    BG_MAGENTA = "\033[45m"
    BG_CYAN = "\033[46m"
    BG_WHITE = "\033[47m"

    @staticmethod
    def gradient_text(text: str, colors: list) -> str:
        result = ""
        for i, char in enumerate(text):
            color = colors[i % len(colors)]
            result += f"{color}{char}"
        return f"{result}{Style.RESET}"

    @staticmethod
    def rainbow_text(text: str) -> str:
        colors = [
            Style.BRIGHT_RED, Style.BRIGHT_YELLOW, Style.GREEN,
            Style.CYAN, Style.BRIGHT_BLUE, Style.MAGENTA
        ]
        return Style.gradient_text(text, colors)

    @staticmethod
    def gold_text(text: str) -> str:
        colors = [Style.YELLOW, Style.BRIGHT_YELLOW, Style.GOLD if hasattr(Style, 'GOLD') else Style.YELLOW]
        return Style.gradient_text(text, colors)

    GOLD = "\033[38;5;220m"
    ORANGE = "\033[38;5;208m"
    PURPLE = "\033[38;5;129m"
    PINK = "\033[38;5;205m"


@dataclass
class GameConfig:
    """Game configuration settings"""
    width: int = 16
    height: int = 16
    initial_speed: float = 0.15
    speed_increment: float = 0.01
    min_speed: float = 0.05
    points_per_food: int = 10


class HighScoreManager:
    """Manages persistent high scores"""

    def __init__(self, save_file: str = "gemini_scores.json"):
        self.save_file = Path.home() / ".gemini_arcade" / save_file
        self.scores: Dict[str, int] = {}
        self._ensure_directory()
        self.load()

    def _ensure_directory(self):
        """Create save directory if it doesn't exist"""
        self.save_file.parent.mkdir(parents=True, exist_ok=True)

    def load(self):
        """Load high scores from file"""
        try:
            if self.save_file.exists():
                with open(self.save_file, 'r') as f:
                    self.scores = json.load(f)
        except Exception as e:
            print(f"Warning: Could not load high scores: {e}")
            self.scores = {}

    def save(self):
        """Save high scores to file"""
        try:
            with open(self.save_file, 'w') as f:
                json.dump(self.scores, f, indent=2)
        except Exception as e:
            print(f"Warning: Could not save high scores: {e}")

    def get_high_score(self, game_name: str) -> int:
        """Get high score for a game"""
        return self.scores.get(game_name, 0)

    def update_high_score(self, game_name: str, score: int) -> bool:
        """Update high score if new score is higher. Returns True if updated."""
        current = self.get_high_score(game_name)
        if score > current:
            self.scores[game_name] = score
            self.save()
            return True
        return False


class GeminiCPU:
    """8-bit CPU with 256 bytes of memory and basic I/O"""

    SCORE_ADDR = 0x100
    HIGH_SCORE_ADDR = 0x101
    VRAM_START = 0x200
    STACK_TOP = 0xFF

    def __init__(self, framebuffer_width: int = 16, framebuffer_height: int = 16):
        self.FB_WIDTH = framebuffer_width
        self.FB_HEIGHT = framebuffer_height
        self.VRAM_SIZE = framebuffer_width * framebuffer_height

        mem_size = self.VRAM_START + self.VRAM_SIZE + 256
        self.memory = [0] * mem_size

        self.reg = {
            'A': 0,
            'B': 0,
            'C': 0,
            'D': 0,
            'PC': 0,
            'SP': self.STACK_TOP
        }
        self.zero_flag = False
        self.carry_flag = False
        self.running = True

        self.last_input = 0
        self.cycles = 0

    def render(self, title: str = "GEMINI", paused: bool = False, info: str = ""):
        """Render the display using ANSI codes"""
        print("\033[H\033[J", end='', flush=True)

        playfield_width = self.FB_WIDTH * 2
        border_color = Style.BRIGHT_CYAN
        shadow_color = Style.BRIGHT_BLACK
        score_color = Style.BRIGHT_GREEN
        high_color = Style.BRIGHT_MAGENTA
        info_color = Style.BRIGHT_WHITE
        title_palette = [
            Style.BRIGHT_MAGENTA,
            Style.BRIGHT_BLUE,
            Style.BRIGHT_CYAN,
            Style.BRIGHT_GREEN,
            Style.BRIGHT_YELLOW,
        ]

        print(f"{shadow_color}{'▄' * (playfield_width + 2)}{Style.RESET}")
        print(f"{border_color}╔{'═' * playfield_width}╗{Style.RESET}")

        title_plain = f"◉ {title} ◉"
        title_colored = Style.gradient_text(title_plain, title_palette)
        left_pad = max(0, (playfield_width - len(title_plain)) // 2)
        right_pad = max(0, playfield_width - left_pad - len(title_plain))
        print(f"{border_color}║{Style.RESET}{' ' * left_pad}{title_colored}{' ' * right_pad}{border_color}║{Style.RESET}")
        print(f"{border_color}╠{'═' * playfield_width}╣{Style.RESET}")

        char_map = {
            0: '  ',
            1: f'{Style.DIM}░░{Style.RESET}',
            2: f' {Style.WHITE}.{Style.RESET}',
            3: f'{Style.BRIGHT_YELLOW}●{Style.RESET} ',
            4: f'{Style.BLUE}▓▓{Style.RESET}',
            5: f'{Style.BRIGHT_GREEN}● {Style.RESET}',
            6: f'{Style.CYAN}▒▒{Style.RESET}',
            7: f'{Style.YELLOW}● {Style.RESET}',
            8: f'{Style.GREEN}● {Style.RESET}',
            9: f'{Style.BRIGHT_GREEN}★★{Style.RESET}',
            10: f'{Style.RED}▓▓{Style.RESET}',
            11: f'{Style.MAGENTA}▒▒{Style.RESET}',
            12: f'{Style.RED}▓▓{Style.RESET}',
            13: f'{Style.ORANGE}▓▓{Style.RESET}',
            14: f'{Style.GOLD}▓▓{Style.RESET}',
            15: f'{Style.BRIGHT_YELLOW}● {Style.RESET}',
        }

        for y in range(self.FB_HEIGHT):
            print(f"{border_color}║{Style.RESET}", end='')
            for x in range(self.FB_WIDTH):
                addr = self.VRAM_START + (y * self.FB_WIDTH) + x
                val = self.memory[addr]
                if val == DisplayChar.EMPTY:
                    checker = (x + y) % 2 == 0
                    char = f"{Style.DIM}{'. ' if checker else '  '}{Style.RESET}"
                else:
                    char = char_map.get(val, '██')
                print(char, end='')
            print(f"{border_color}║{Style.RESET}")

        print(f"{border_color}╠{'═' * playfield_width}╣{Style.RESET}")

        score = self.memory[self.SCORE_ADDR]
        high_score = self.memory[self.HIGH_SCORE_ADDR]
        score_label = " SCORE "
        high_label = " HIGH "
        visible_score_len = len(f"{score_label}{score:<4}   {high_label}{high_score:<4}")
        pad_total = max(0, playfield_width - visible_score_len)
        left_pad = pad_total // 2
        right_pad = pad_total - left_pad
        score_text = (
            f"{Style.BRIGHT_WHITE}{score_label}{Style.RESET}"
            f"{score_color}{score:<4}{Style.RESET}"
            f"   {Style.BRIGHT_WHITE}{high_label}{Style.RESET}"
            f"{high_color}{high_score:<4}{Style.RESET}"
        )
        print(f"{border_color}║{Style.RESET}{' ' * left_pad}{score_text}{' ' * right_pad}{border_color}║{Style.RESET}")

        if paused:
            paused_text = "== PAUSED =="
            visible_paused_len = len(paused_text)
            paused_pad = max(0, playfield_width - visible_paused_len)
            paused_left = paused_pad // 2
            paused_right = paused_pad - paused_left
            paused_badge = f"{Style.BRIGHT_RED}{Style.BLINK}{paused_text}{Style.RESET}"
            print(f"{border_color}║{Style.RESET}{' ' * paused_left}{paused_badge}{' ' * paused_right}{border_color}║{Style.RESET}")

        if info:
            print(f"{border_color}║{Style.RESET}{info_color}{info:^{playfield_width}}{Style.RESET}{border_color}║{Style.RESET}")

        print(f"{border_color}╠{'═' * playfield_width}╣{Style.RESET}")
        
        # Two-line centered controls display (max 32 chars wide)
        labels = "Move    Pause   Reset   Quit"
        keys = "←↑↓→      P       R       Q"
        
        # Calculate padding based on visible length (not including color codes)
        visible_label_len = len(labels)
        label_pad = max(0, playfield_width - visible_label_len)
        label_left = label_pad // 2
        label_right = label_pad - label_left
        
        visible_keys_len = len(keys)
        keys_pad = max(0, playfield_width - visible_keys_len)
        keys_left = keys_pad // 2
        keys_right = keys_pad - keys_left
        
        print(
            f"{border_color}║{Style.RESET}"
            f"{' ' * label_left}{Style.DIM}{labels}{Style.RESET}{' ' * label_right}"
            f"{border_color}║{Style.RESET}"
        )
        print(
            f"{border_color}║{Style.RESET}"
            f"{' ' * keys_left}{Style.DIM}{keys}{Style.RESET}{' ' * keys_right}"
            f"{border_color}║{Style.RESET}"
        )
        print(f"{border_color}╚{'═' * playfield_width}╝{Style.RESET}")
        print(f"{shadow_color}{'▀' * (playfield_width + 2)}{Style.RESET}")

    def step(self):
        """Execute one instruction"""
        pc = self.reg['PC']
        if pc >= len(self.memory):
            self.running = False
            return

        opcode = self.memory[pc]
        self.cycles += 1

        if opcode == Opcode.NOP:
            self.reg['PC'] += 1
        elif opcode == Opcode.LDA_IMM:
            self.reg['A'] = self.memory[pc + 1]
            self.reg['PC'] += 2
        elif opcode == Opcode.STA_ABS:
            addr = self._read_address(pc + 1)
            if addr < len(self.memory):
                self.memory[addr] = self.reg['A']
            self.reg['PC'] += 3
        elif opcode == Opcode.ADD:
            result = self.reg['A'] + self.reg['B']
            self.carry_flag = result > 0xFF
            self.reg['A'] = result & 0xFF
            self.zero_flag = self.reg['A'] == 0
            self.reg['PC'] += 1
        elif opcode == Opcode.LDB_IMM:
            self.reg['B'] = self.memory[pc + 1]
            self.reg['PC'] += 2
        elif opcode == Opcode.CMP:
            self.zero_flag = (self.reg['A'] == self.reg['B'])
            self.reg['PC'] += 1
        elif opcode == Opcode.JMP:
            self.reg['PC'] = self._read_address(pc + 1)
        elif opcode == Opcode.JZ:
            if self.zero_flag:
                self.reg['PC'] = self._read_address(pc + 1)
            else:
                self.reg['PC'] += 3
        elif opcode == Opcode.INP:
            self.reg['A'] = self.last_input if self.last_input != 0 else 0
            self.last_input = 0
            self.reg['PC'] += 1
        elif opcode == Opcode.SUB:
            result = self.reg['A'] - self.reg['B']
            self.carry_flag = result < 0
            self.reg['A'] = result & 0xFF
            self.zero_flag = self.reg['A'] == 0
            self.reg['PC'] += 1
        elif opcode == Opcode.LDC_IMM:
            self.reg['C'] = self.memory[pc + 1]
            self.reg['PC'] += 2
        elif opcode == Opcode.LDD_IMM:
            self.reg['D'] = self.memory[pc + 1]
            self.reg['PC'] += 2
        elif opcode == Opcode.INC:
            self.reg['A'] = (self.reg['A'] + 1) & 0xFF
            self.zero_flag = self.reg['A'] == 0
            self.reg['PC'] += 1
        elif opcode == Opcode.DEC:
            self.reg['A'] = (self.reg['A'] - 1) & 0xFF
            self.zero_flag = self.reg['A'] == 0
            self.reg['PC'] += 1
        elif opcode == Opcode.JNZ:
            if not self.zero_flag:
                self.reg['PC'] = self._read_address(pc + 1)
            else:
                self.reg['PC'] += 3
        elif opcode == Opcode.LDA_ABS:
            addr = self._read_address(pc + 1)
            if addr < len(self.memory):
                self.reg['A'] = self.memory[addr]
            self.reg['PC'] += 3
        elif opcode == Opcode.LDA_IDX:
            addr = self.reg['B'] + self.reg['C']
            if addr < len(self.memory):
                self.reg['A'] = self.memory[addr]
            self.reg['PC'] += 1
        elif opcode == Opcode.STA_IDX:
            addr = self.reg['B'] + self.reg['C']
            if addr < len(self.memory):
                self.memory[addr] = self.reg['A']
            self.reg['PC'] += 1
        elif opcode == Opcode.CALL:
            ret_addr = pc + 3
            self._push(ret_addr)
            self.reg['PC'] = self._read_address(pc + 1)
        elif opcode == Opcode.RET:
            self.reg['PC'] = self._pop()
        elif opcode == Opcode.MOV_BA:
            self.reg['B'] = self.reg['A']
            self.reg['PC'] += 1
        elif opcode == Opcode.MOV_AB:
            self.reg['A'] = self.reg['B']
            self.reg['PC'] += 1
        elif opcode == Opcode.MOV_CA:
            self.reg['C'] = self.reg['A']
            self.reg['PC'] += 1
        elif opcode == Opcode.MOV_AC:
            self.reg['A'] = self.reg['C']
            self.reg['PC'] += 1
        elif opcode == Opcode.MOV_DA:
            self.reg['D'] = self.reg['A']
            self.reg['PC'] += 1
        elif opcode == Opcode.MOV_AD:
            self.reg['A'] = self.reg['D']
            self.reg['PC'] += 1
        elif opcode == Opcode.AND:
            self.reg['A'] = self.reg['A'] & self.reg['B']
            self.zero_flag = self.reg['A'] == 0
            self.reg['PC'] += 1
        elif opcode == Opcode.OR:
            self.reg['A'] = self.reg['A'] | self.reg['B']
            self.zero_flag = self.reg['A'] == 0
            self.reg['PC'] += 1
        elif opcode == Opcode.HALT:
            self.running = False
        else:
            self.reg['PC'] += 1

    def _read_address(self, addr: int) -> int:
        """Read 16-bit address from memory (little-endian)"""
        return self.memory[addr] | (self.memory[addr + 1] << 8)

    def _push(self, value: int):
        """Push 16-bit value onto stack"""
        self.memory[self.reg['SP']] = value & 0xFF
        self.reg['SP'] = (self.reg['SP'] - 1) & 0xFF
        self.memory[self.reg['SP']] = (value >> 8) & 0xFF
        self.reg['SP'] = (self.reg['SP'] - 1) & 0xFF

    def _pop(self) -> int:
        """Pop 16-bit value from stack"""
        self.reg['SP'] = (self.reg['SP'] + 1) & 0xFF
        high = self.memory[self.reg['SP']]
        self.reg['SP'] = (self.reg['SP'] + 1) & 0xFF
        low = self.memory[self.reg['SP']]
        return (high << 8) | low

    def get_vram_pixel(self, x: int, y: int) -> int:
        """Get pixel value from VRAM"""
        if 0 <= x < self.FB_WIDTH and 0 <= y < self.FB_HEIGHT:
            addr = self.VRAM_START + (y * self.FB_WIDTH) + x
            return self.memory[addr]
        return 0

    def set_vram_pixel(self, x: int, y: int, value: int):
        """Set pixel value in VRAM"""
        if 0 <= x < self.FB_WIDTH and 0 <= y < self.FB_HEIGHT:
            addr = self.VRAM_START + (y * self.FB_WIDTH) + x
            self.memory[addr] = value & 0xFF

    def clear_vram(self):
        """Clear all of VRAM"""
        for i in range(self.VRAM_SIZE):
            self.memory[self.VRAM_START + i] = 0

    def load_program(self, program: List[int], start_addr: int = 0):
        """Load a program into memory"""
        for i, val in enumerate(program):
            if start_addr + i < len(self.memory):
                self.memory[start_addr + i] = val


class Game(ABC):
    """Base class for all games"""

    def __init__(self, cpu: GeminiCPU, high_score_manager: HighScoreManager):
        self.cpu = cpu
        self.high_score_manager = high_score_manager
        self.width = cpu.FB_WIDTH
        self.height = cpu.FB_HEIGHT
        self.score = 0
        self.game_over = False
        self.game_speed = 0.15

    @abstractmethod
    def get_name(self) -> str:
        """Get game name"""
        pass

    @abstractmethod
    def reset(self):
        """Reset game state"""
        pass

    @abstractmethod
    def update(self):
        """Update game state"""
        pass

    @abstractmethod
    def handle_input(self, key: str):
        """Handle input"""
        pass

    def load_high_score(self):
        """Load high score from manager"""
        high_score = self.high_score_manager.get_high_score(self.get_name())
        self.cpu.memory[self.cpu.HIGH_SCORE_ADDR] = min(high_score, 255)
        return high_score

    def save_high_score(self):
        """Save high score if it's a new record"""
        return self.high_score_manager.update_high_score(self.get_name(), self.score)


class SnakeGame(Game):
    """Classic Snake game"""

    def __init__(self, cpu: GeminiCPU, high_score_manager: HighScoreManager):
        super().__init__(cpu, high_score_manager)
        self.config = GameConfig()
        self.snake: List[Tuple[int, int]] = []
        self.direction: Tuple[int, int] = (0, 0)
        self.food: Tuple[int, int] = (0, 0)
        self.game_speed = self.config.initial_speed
        self.reset()

    def get_name(self) -> str:
        return "Snake"

    def reset(self):
        """Reset game state"""
        if self.score > 0:
            self.save_high_score()

        self.load_high_score()
        self.snake = [(self.width // 2, self.height // 2)]
        self.direction = (1, 0)
        self.food = self.place_food()
        self.score = 0
        self.game_over = False
        self.game_speed = self.config.initial_speed
        self.update_display()

    def place_food(self) -> Tuple[int, int]:
        """Place food in random empty location"""
        for _ in range(100):
            x = random.randint(0, self.width - 1)
            y = random.randint(0, self.height - 1)
            if (x, y) not in self.snake:
                return (x, y)
        return (0, 0)

    def update_display(self):
        """Update VRAM with current game state"""
        vram_end = self.cpu.VRAM_START + self.cpu.VRAM_SIZE
        for i in range(self.cpu.VRAM_START, vram_end):
            self.cpu.memory[i] = DisplayChar.EMPTY

        for i, (x, y) in enumerate(self.snake):
            if 0 <= x < self.width and 0 <= y < self.height:
                addr = self.cpu.VRAM_START + (y * self.width) + x
                if i == 0:
                    self.cpu.memory[addr] = 3
                else:
                    self.cpu.memory[addr] = 8

        fx, fy = self.food
        if 0 <= fx < self.width and 0 <= fy < self.height:
            addr = self.cpu.VRAM_START + (fy * self.width) + fx
            self.cpu.memory[addr] = 5

        self.cpu.memory[self.cpu.SCORE_ADDR] = min(self.score, 255)

    def update(self):
        """Update game state"""
        if self.game_over:
            return

        head_x, head_y = self.snake[0]
        dx, dy = self.direction
        new_x = head_x + dx
        new_y = head_y + dy

        if not (0 <= new_x < self.width and 0 <= new_y < self.height):
            self.game_over = True
            self.save_high_score()
            return

        if (new_x, new_y) in self.snake:
            self.game_over = True
            self.save_high_score()
            return

        self.snake.insert(0, (new_x, new_y))

        if (new_x, new_y) == self.food:
            self.score += self.config.points_per_food
            self.food = self.place_food()
            if self.game_speed > self.config.min_speed:
                self.game_speed = max(self.config.min_speed,
                                     self.game_speed - self.config.speed_increment)
        else:
            self.snake.pop()

        self.update_display()

    def handle_input(self, key: str):
        """Handle input"""
        direction_map = {
            'UP': (0, -1),
            'DOWN': (0, 1),
            'LEFT': (-1, 0),
            'RIGHT': (1, 0)
        }
        if key in direction_map:
            new_dir = direction_map[key]
            curr_dx, curr_dy = self.direction
            if new_dir != (-curr_dx, -curr_dy):
                self.direction = new_dir


class PongGame(Game):
    """Single-player Pong game"""

    def __init__(self, cpu: GeminiCPU, high_score_manager: HighScoreManager):
        super().__init__(cpu, high_score_manager)
        self.paddle_y = 0
        self.ball_x = 0
        self.ball_y = 0
        self.ball_dx = 0
        self.ball_dy = 0
        self.paddle_height = 4
        self.game_speed = 0.08
        self.reset()

    def get_name(self) -> str:
        return "Pong"

    def reset(self):
        """Reset game state"""
        if self.score > 0:
            self.save_high_score()

        self.load_high_score()
        self.paddle_y = self.height // 2 - self.paddle_height // 2
        self.ball_x = self.width // 2
        self.ball_y = self.height // 2
        self.ball_dx = 1
        self.ball_dy = random.choice([-1, 1])
        self.score = 0
        self.game_over = False
        self.update_display()

    def update_display(self):
        """Update VRAM"""
        vram_end = self.cpu.VRAM_START + self.cpu.VRAM_SIZE
        for i in range(self.cpu.VRAM_START, vram_end):
            self.cpu.memory[i] = DisplayChar.EMPTY

        # Draw paddle (left side)
        for i in range(self.paddle_height):
            y = self.paddle_y + i
            if 0 <= y < self.height:
                addr = self.cpu.VRAM_START + y * self.width
                self.cpu.memory[addr] = 6

        # Draw ball
        if 0 <= self.ball_x < self.width and 0 <= self.ball_y < self.height:
            addr = self.cpu.VRAM_START + self.ball_y * self.width + self.ball_x
            self.cpu.memory[addr] = 7

        self.cpu.memory[self.cpu.SCORE_ADDR] = min(self.score, 255)

    def update(self):
        """Update game state"""
        if self.game_over:
            return

        # Move ball
        self.ball_x += self.ball_dx
        self.ball_y += self.ball_dy

        # Bounce off top/bottom
        if self.ball_y <= 0 or self.ball_y >= self.height - 1:
            self.ball_dy = -self.ball_dy
            self.ball_y = max(0, min(self.height - 1, self.ball_y))

        # Bounce off right wall
        if self.ball_x >= self.width - 1:
            self.ball_dx = -self.ball_dx
            self.score += 1

        # Check paddle collision
        if self.ball_x == 0:
            if self.paddle_y <= self.ball_y < self.paddle_y + self.paddle_height:
                self.ball_dx = -self.ball_dx
                self.ball_x = 1
                self.score += 5
            else:
                self.game_over = True
                self.save_high_score()

        self.update_display()

    def handle_input(self, key: str):
        """Handle input"""
        if key == 'UP':
            self.paddle_y = max(0, self.paddle_y - 2)
            self.update_display()
        elif key == 'DOWN':
            self.paddle_y = min(self.height - self.paddle_height, self.paddle_y + 2)
            self.update_display()


class BreakoutGame(Game):
    """Breakout/Arkanoid style game"""

    def __init__(self, cpu: GeminiCPU, high_score_manager: HighScoreManager):
        super().__init__(cpu, high_score_manager)
        self.paddle_x = 0
        self.paddle_width = 4
        self.ball_x = 0
        self.ball_y = 0
        self.ball_dx = 0
        self.ball_dy = 0
        self.bricks: List[Tuple[int, int]] = []
        self.lives = 3
        self.game_speed = 0.1
        self.reset()

    def get_name(self) -> str:
        return "Breakout"

    def reset(self):
        """Reset game state"""
        if self.score > 0:
            self.save_high_score()

        self.load_high_score()
        self.paddle_x = self.width // 2 - self.paddle_width // 2
        self.ball_x = self.width // 2
        self.ball_y = self.height - 3
        self.ball_dx = random.choice([-1, 1])
        self.ball_dy = -1

        # Create bricks
        self.bricks = []
        for y in range(2, 6):
            for x in range(2, self.width - 2):
                self.bricks.append((x, y))

        self.score = 0
        self.game_over = False
        self.lives = 3
        self.update_display()

    def update_display(self):
        """Update VRAM"""
        vram_end = self.cpu.VRAM_START + self.cpu.VRAM_SIZE
        for i in range(self.cpu.VRAM_START, vram_end):
            self.cpu.memory[i] = DisplayChar.EMPTY

        # Draw bricks
        for x, y in self.bricks:
            addr = self.cpu.VRAM_START + y * self.width + x
            self.cpu.memory[addr] = 10

        # Draw paddle
        for i in range(self.paddle_width):
            x = self.paddle_x + i
            if 0 <= x < self.width:
                addr = self.cpu.VRAM_START + (self.height - 1) * self.width + x
                self.cpu.memory[addr] = 6

        # Draw ball
        if 0 <= self.ball_x < self.width and 0 <= self.ball_y < self.height:
            addr = self.cpu.VRAM_START + self.ball_y * self.width + self.ball_x
            self.cpu.memory[addr] = 7

        self.cpu.memory[self.cpu.SCORE_ADDR] = min(self.score, 255)

    def update(self):
        """Update game state"""
        if self.game_over:
            return

        next_x = self.ball_x + self.ball_dx
        next_y = self.ball_y + self.ball_dy

        # --- Brick collision (check before moving) ---
        hit_x = (next_x, self.ball_y) in self.bricks
        hit_y = (self.ball_x, next_y) in self.bricks
        hit_corner = (next_x, next_y) in self.bricks

        if hit_x and hit_y:
            # Corner hit: both axes blocked, reverse both
            self.bricks.remove((next_x, self.ball_y))
            self.bricks.remove((self.ball_x, next_y))
            self.ball_dx = -self.ball_dx
            self.ball_dy = -self.ball_dy
            self.score += 20
        elif hit_x:
            # Side hit: reverse x
            self.bricks.remove((next_x, self.ball_y))
            self.ball_dx = -self.ball_dx
            self.score += 10
        elif hit_y:
            # Top/bottom hit: reverse y
            self.bricks.remove((self.ball_x, next_y))
            self.ball_dy = -self.ball_dy
            self.score += 10
        elif hit_corner:
            # Diagonal corner hit with no adjacent bricks: reverse both
            self.bricks.remove((next_x, next_y))
            self.ball_dx = -self.ball_dx
            self.ball_dy = -self.ball_dy
            self.score += 10

        # Win condition
        if not self.bricks:
            self.game_over = True
            self.save_high_score()
            self.update_display()
            return

        # --- Move ball ---
        self.ball_x += self.ball_dx
        self.ball_y += self.ball_dy

        # --- Wall bounces ---
        if self.ball_x <= 0 or self.ball_x >= self.width - 1:
            self.ball_dx = -self.ball_dx
            self.ball_x = max(0, min(self.width - 1, self.ball_x))

        if self.ball_y <= 0:
            self.ball_dy = -self.ball_dy
            self.ball_y = 1

        # --- Paddle collision ---
        if self.ball_y >= self.height - 2:
            if self.paddle_x <= self.ball_x < self.paddle_x + self.paddle_width:
                self.ball_y = self.height - 2
                self.ball_dy = -1
                # Only force direction on paddle edges; keep current dx in the middle
                pos_in_paddle = self.ball_x - self.paddle_x
                if pos_in_paddle == 0:
                    self.ball_dx = -1
                elif pos_in_paddle == self.paddle_width - 1:
                    self.ball_dx = 1
                # else: keep current ball_dx as-is
            else:
                # Ball fell off
                self.lives -= 1
                if self.lives <= 0:
                    self.game_over = True
                    self.save_high_score()
                    self.update_display()
                    return
                # Respawn ball above paddle
                self.ball_x = self.paddle_x + self.paddle_width // 2
                self.ball_y = self.height - 3
                self.ball_dx = random.choice([-1, 1])
                self.ball_dy = -1

        self.update_display()

    def handle_input(self, key: str):
        """Handle input"""
        if key == 'LEFT':
            self.paddle_x = max(0, self.paddle_x - 2)
            self.update_display()
        elif key == 'RIGHT':
            self.paddle_x = min(self.width - self.paddle_width, self.paddle_x + 2)
            self.update_display()


class RacingGame(Game):
    """Simple top-down racing game"""

    def __init__(self, cpu: GeminiCPU, high_score_manager: HighScoreManager):
        super().__init__(cpu, high_score_manager)
        self.car_x = 0
        self.obstacles: List[Tuple[int, int]] = []
        self.scroll_offset = 0
        self.game_speed = 0.12
        self.reset()

    def get_name(self) -> str:
        return "Racing"

    def reset(self):
        """Reset game state"""
        if self.score > 0:
            self.save_high_score()

        self.load_high_score()
        self.car_x = self.width // 2
        self.obstacles = []
        self.scroll_offset = 0
        self.score = 0
        self.game_over = False
        self.update_display()

    def spawn_obstacle(self):
        """Spawn a new obstacle"""
        if random.random() < 0.3:
            x = random.randint(2, self.width - 3)
            self.obstacles.append((x, 0))

    def update_display(self):
        """Update VRAM"""
        vram_end = self.cpu.VRAM_START + self.cpu.VRAM_SIZE
        for i in range(self.cpu.VRAM_START, vram_end):
            self.cpu.memory[i] = DisplayChar.EMPTY

        # Draw road edges
        for y in range(self.height):
            addr_left = self.cpu.VRAM_START + y * self.width
            addr_right = self.cpu.VRAM_START + y * self.width + (self.width - 1)
            self.cpu.memory[addr_left] = 4
            self.cpu.memory[addr_right] = 4

        # Draw obstacles
        for x, y in self.obstacles:
            if 0 <= y < self.height and 0 <= x < self.width:
                addr = self.cpu.VRAM_START + y * self.width + x
                self.cpu.memory[addr] = 12

        # Draw car
        car_y = self.height - 2
        if 0 <= self.car_x < self.width:
            addr = self.cpu.VRAM_START + car_y * self.width + self.car_x
            self.cpu.memory[addr] = 11

        self.cpu.memory[self.cpu.SCORE_ADDR] = min(self.score, 255)

    def update(self):
        """Update game state"""
        if self.game_over:
            return

        # Move obstacles down
        new_obstacles = []
        for x, y in self.obstacles:
            y += 1
            if y < self.height:
                new_obstacles.append((x, y))
        self.obstacles = new_obstacles

        # Spawn new obstacles
        self.spawn_obstacle()

        # Check collision
        car_y = self.height - 2
        for x, y in self.obstacles:
            if x == self.car_x and y == car_y:
                self.game_over = True
                self.save_high_score()
                return

        self.score += 1
        self.update_display()

    def handle_input(self, key: str):
        """Handle input"""
        if key == 'LEFT':
            self.car_x = max(1, self.car_x - 1)
            self.update_display()
        elif key == 'RIGHT':
            self.car_x = min(self.width - 2, self.car_x + 1)
            self.update_display()


class PacManGame(Game):
    """Classic Pac-Man arcade game"""

    # Maze: 0=corridor, 1=wall, 2=dot, 3=power pellet
    MAZE_TEMPLATE = [
        [1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1],
        [1,2,2,2,2,2,2,1,2,2,2,2,2,2,2,1],
        [1,2,1,1,2,1,2,1,2,1,1,2,1,1,2,1],
        [1,3,1,1,2,2,2,2,2,1,1,2,2,2,2,1],
        [1,2,2,2,2,1,1,1,1,1,2,2,1,1,1,1],
        [1,2,1,1,2,2,2,2,2,2,2,1,1,1,2,1],
        [1,2,1,1,2,1,1,1,1,2,2,1,1,1,2,1],
        [1,2,2,2,2,1,2,0,0,2,1,2,2,2,2,1],
        [1,2,1,1,2,1,2,1,1,1,1,1,2,1,1,1],
        [1,2,1,1,2,1,2,2,2,2,2,2,2,1,1,1],
        [1,2,2,2,2,1,1,1,1,1,1,2,1,2,2,1],
        [1,2,1,1,2,2,2,2,2,2,1,2,1,1,2,1],
        [1,2,1,1,2,1,1,1,1,2,1,2,1,1,2,1],
        [1,2,2,2,2,1,1,1,1,2,2,2,2,2,3,1],
        [1,2,2,1,2,1,1,1,1,2,1,1,1,1,1,1],
        [1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1],
    ]

    def __init__(self, cpu: GeminiCPU, high_score_manager: HighScoreManager):
        super().__init__(cpu, high_score_manager)
        self.game_speed = 0.12
        self.maze: List[List[int]] = []
        self.player_x = 0
        self.player_y = 0
        self.player_dx = 0
        self.player_dy = 0
        self.next_dx = 0
        self.next_dy = 0
        self.ghosts: List['_Ghost'] = []
        self.power_mode = 0
        self.lives = 3
        self.total_dots = 0
        self.dots_remaining = 0
        self.reset()

    def get_name(self) -> str:
        return "Pac-Man"

    def reset(self):
        if self.score > 0:
            self.save_high_score()

        self.load_high_score()
        # Copy maze template
        self.maze = [row[:] for row in self.MAZE_TEMPLATE]
        self.total_dots = sum(row.count(2) + row.count(3) for row in self.maze)
        self.dots_remaining = self.total_dots

        # Player starts bottom-center in a valid corridor
        self.player_x, self.player_y = 9, 13
        self.player_dx, self.player_dy = 0, 0
        self.next_dx, self.next_dy = 0, 0

        # 4 Ghosts start in center
        self.ghosts = [
            _Ghost(7, 7, 'R'),
            _Ghost(8, 7, 'P'),
            _Ghost(7, 8, 'B'),
            _Ghost(8, 8, 'O'),
        ]

        self.power_mode = 0
        self.lives = 3
        self.score = 0
        self.game_over = False
        self.update_display()

    def handle_input(self, key: str):
        if key == 'UP':
            self.next_dx, self.next_dy = 0, -1
        elif key == 'DOWN':
            self.next_dx, self.next_dy = 0, 1
        elif key == 'LEFT':
            self.next_dx, self.next_dy = -1, 0
        elif key == 'RIGHT':
            self.next_dx, self.next_dy = 1, 0

    def update(self):
        if self.game_over:
            return

        # Try to change direction
        nx = self.player_x + self.next_dx
        ny = self.player_y + self.next_dy
        if 0 <= nx < self.width and 0 <= ny < self.height and self.maze[ny][nx] != 1:
            self.player_dx, self.player_dy = self.next_dx, self.next_dy

        # Move player
        nx = self.player_x + self.player_dx
        ny = self.player_y + self.player_dy
        if 0 <= nx < self.width and 0 <= ny < self.height and self.maze[ny][nx] != 1:
            self.player_x, self.player_y = nx, ny

        # Eat dots
        cell = self.maze[self.player_y][self.player_x]
        if cell == 2:  # regular dot
            self.maze[self.player_y][self.player_x] = 0
            self.score += 10
            self.dots_remaining -= 1
        elif cell == 3:  # power pellet
            self.maze[self.player_y][self.player_x] = 0
            self.score += 50
            self.dots_remaining -= 1
            self.power_mode = 80  # ~8 seconds at 0.12 speed
            for g in self.ghosts:
                g.scared = True

        # Power mode countdown
        if self.power_mode > 0:
            self.power_mode -= 1
            if self.power_mode == 0:
                for g in self.ghosts:
                    g.scared = False

        # Move ghosts - each has different AI behavior
        for i, g in enumerate(self.ghosts):
            if not g.eaten:
                if g.scared:
                    # All scared ghosts run to opposite corner
                    tx = 0 if self.player_x > 8 else 15
                    ty = 0 if self.player_y > 8 else 15
                    g.move_toward(tx, ty, self.maze, self.width, self.height)
                else:
                    # Each ghost has unique behavior
                    if i == 0:  # Red: direct chase
                        g.move_toward(self.player_x, self.player_y, self.maze, self.width, self.height)
                    elif i == 1:  # Pink: ambush ahead of player
                        target_x = self.player_x + self.player_dx * 4
                        target_y = self.player_y + self.player_dy * 4
                        g.move_toward(target_x, target_y, self.maze, self.width, self.height)
                    elif i == 2:  # Blue: patrol corners
                        corners = [(1,1), (14,1), (1,14), (14,14)]
                        target = corners[(g.x + g.y) % 4]
                        g.move_toward(target[0], target[1], self.maze, self.width, self.height)
                    else:  # Orange: scatter / semi-random
                        if abs(self.player_x - g.x) + abs(self.player_y - g.y) < 8:
                            # Close to player: run to corner
                            g.move_toward(1, 1, self.maze, self.width, self.height)
                        else:
                            # Far from player: chase
                            g.move_toward(self.player_x, self.player_y, self.maze, self.width, self.height)

        # Check ghost collisions
        for g in self.ghosts:
            if g.x == self.player_x and g.y == self.player_y:
                if g.scared and not g.eaten:
                    # Eat ghost
                    self.score += 200
                    g.eaten = True
                    g.respawn_timer = 50
                elif not g.scared and not g.eaten:
                    # Player dies
                    self.lives -= 1
                    if self.lives <= 0:
                        self.game_over = True
                        self.save_high_score()
                    else:
                        # Reset positions
                        self.player_x, self.player_y = 9, 13
                        self.player_dx, self.player_dy = 0, 0
                        for gh in self.ghosts:
                            gh.reset_pos()

        # Ghost respawn
        for g in self.ghosts:
            if g.eaten:
                g.respawn_timer -= 1
                if g.respawn_timer <= 0:
                    g.reset_pos()
                    g.eaten = False
                    g.scared = False

        # Win condition
        if self.dots_remaining == 0:
            self.game_over = True
            self.save_high_score()

        self.update_display()

    def update_display(self):
        vram_end = self.cpu.VRAM_START + self.cpu.VRAM_SIZE
        for i in range(self.cpu.VRAM_START, vram_end):
            self.cpu.memory[i] = DisplayChar.EMPTY

        # Draw maze
        for y in range(self.height):
            for x in range(self.width):
                addr = self.cpu.VRAM_START + y * self.width + x
                cell = self.maze[y][x]
                if cell == 1:
                    self.cpu.memory[addr] = 4
                elif cell == 2:
                    self.cpu.memory[addr] = 2
                elif cell == 3:
                    self.cpu.memory[addr] = 14

        # Draw ghosts
        for g in self.ghosts:
            if not g.eaten:
                addr = self.cpu.VRAM_START + g.y * self.width + g.x
                if g.scared:
                    self.cpu.memory[addr] = 1
                else:
                    self.cpu.memory[addr] = 12

        # Draw player
        addr = self.cpu.VRAM_START + self.player_y * self.width + self.player_x
        self.cpu.memory[addr] = 15

        self.cpu.memory[self.cpu.SCORE_ADDR] = min(self.score, 255)


class _Ghost:
    """Ghost AI for Pac-Man"""
    __slots__ = ('x', 'y', 'start_x', 'start_y', 'color', 'scared', 'eaten', 'respawn_timer')

    def __init__(self, x: int, y: int, color: str):
        self.x = x
        self.y = y
        self.start_x = x
        self.start_y = y
        self.color = color
        self.scared = False
        self.eaten = False
        self.respawn_timer = 0

    def reset_pos(self):
        self.x = self.start_x
        self.y = self.start_y

    def move_toward(self, target_x: int, target_y: int, maze: list, width: int, height: int):
        """Simple AI: pick direction that gets closer to target"""
        dirs = [(0, -1), (0, 1), (-1, 0), (1, 0)]
        best_pos = None
        best_dist = 9999

        for dx, dy in dirs:
            nx, ny = self.x + dx, self.y + dy
            if 0 <= nx < width and 0 <= ny < height and maze[ny][nx] != 1:
                dist = abs(nx - target_x) + abs(ny - target_y)
                if dist < best_dist:
                    best_dist = dist
                    best_pos = (nx, ny)

        if best_pos:
            self.x, self.y = best_pos


class InputHandler:
    """Platform-independent input handler"""

    def __init__(self):
        self.old_settings = None

    def __enter__(self):
        """Setup terminal for raw input"""
        if os.name != 'nt':
            try:
                import termios
                import tty
                self.old_settings = termios.tcgetattr(sys.stdin)
                tty.setcbreak(sys.stdin.fileno())
            except Exception:
                pass
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Restore terminal settings"""
        if self.old_settings:
            import termios
            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, self.old_settings)

    def get_input(self) -> Optional[str]:
        """Get non-blocking input"""
        if os.name == 'nt':
            return self._get_windows_input()
        else:
            return self._get_unix_input()

    def _get_windows_input(self) -> Optional[str]:
        """Get input on Windows"""
        try:
            import msvcrt
            if msvcrt.kbhit():
                char = msvcrt.getch()
                if char == b'\xe0':
                    char = msvcrt.getch()
                    key_map = {b'H': 'UP', b'P': 'DOWN', 
                              b'K': 'LEFT', b'M': 'RIGHT'}
                    return key_map.get(char)
                else:
                    return char.decode('utf-8', errors='ignore').lower()
        except ImportError:
            pass
        return None

    def _get_unix_input(self) -> Optional[str]:
        """Get input on Unix-like systems"""
        try:
            import select
            if select.select([sys.stdin], [], [], 0.0)[0]:
                char = sys.stdin.read(1)

                if char == '\x1b':
                    next1 = sys.stdin.read(1)
                    if next1 == '[':
                        next2 = sys.stdin.read(1)
                        key_map = {'A': 'UP', 'B': 'DOWN',
                                  'C': 'RIGHT', 'D': 'LEFT'}
                        return key_map.get(next2)
                elif char == '\x03':
                    return 'q'
                else:
                    return char.lower()
        except Exception:
            pass
        return None


class GEMINIShell:
    """Enhanced Command Line Interface for GEMINI-1"""
    def __init__(self, cpu: GeminiCPU):
        self.cpu = cpu
        self.running = True
        self.history = []

    def print_banner(self):
        """Print enhanced shell banner"""
        print("\033[2J\033[H")
        print()
        print(f"  {Style.BRIGHT_CYAN}╔{'═' * 60}╗{Style.RESET}")
        print(f"  {Style.BRIGHT_CYAN}║{Style.RESET}  {Style.BRIGHT_WHITE}{Style.BOLD}GEMINI-1 MICROCOMPUTER - INTERACTIVE SHELL{Style.RESET}              {Style.BRIGHT_CYAN}║{Style.RESET}")
        print(f"  {Style.BRIGHT_CYAN}║{Style.RESET}  {Style.DIM}8-bit CPU | 64KB RAM | 16x16 VRAM{Style.RESET}                      {Style.BRIGHT_CYAN}║{Style.RESET}")
        print(f"  {Style.BRIGHT_CYAN}╠{'═' * 60}╣{Style.RESET}")
        print(f"  {Style.BRIGHT_CYAN}║{Style.RESET}  {Style.BRIGHT_YELLOW}Type 'HELP' for available commands{Style.RESET}                    {Style.BRIGHT_CYAN}║{Style.RESET}")
        print(f"  {Style.BRIGHT_CYAN}╚{'═' * 60}╝{Style.RESET}")
        print()

    def print_help(self):
        """Print enhanced help message"""
        commands = [
            ("HELP", "Show this help message"),
            ("STATUS", "Display CPU status and registers"),
            ("MEM <addr>", "Read memory at address (hex or dec)"),
            ("PEEK <addr>", "Peek at memory address (alias for MEM)"),
            ("POKE <addr> <val>", "Write value to memory address"),
            ("REGS", "Display all CPU registers"),
            ("VRAM", "Display video RAM contents"),
            ("RESET", "Reset CPU to initial state"),
            ("RUN [addr]", "Execute program from address"),
            ("STEP [n]", "Execute n instructions (default 1)"),
            ("DUMP <start> <end>", "Dump memory range"),
            ("FILL <start> <end> <val>", "Fill memory range with value"),
            ("CLEAR", "Clear the screen"),
            ("HISTORY", "Show command history"),
            ("DEMO", "Run a demo pattern on VRAM"),
            ("INFO", "Display system information"),
            ("VER", "Display version information"),
            ("EXIT", "Exit the shell"),
        ]
        
        print(f"\n  {Style.BRIGHT_WHITE}{Style.BOLD}Available Commands:{Style.RESET}\n")
        for cmd, desc in commands:
            cmd_colored = f"{Style.BRIGHT_CYAN}{cmd:22s}{Style.RESET}"
            print(f"    {cmd_colored} {Style.DIM}{desc}{Style.RESET}")
        print()

    def print_status(self):
        """Print CPU status"""
        print(f"\n  {Style.BRIGHT_WHITE}{Style.BOLD}CPU Status:{Style.RESET}")
        print(f"  {Style.BRIGHT_CYAN}├─{Style.RESET} Running: {Style.BRIGHT_GREEN if self.cpu.running else Style.BRIGHT_RED}{self.cpu.running}{Style.RESET}")
        print(f"  {Style.BRIGHT_CYAN}├─{Style.RESET} PC: {Style.BRIGHT_YELLOW}0x{self.cpu.reg['PC']:02X}{Style.RESET} ({self.cpu.reg['PC']})")
        print(f"  {Style.BRIGHT_CYAN}├─{Style.RESET} SP: {Style.BRIGHT_YELLOW}0x{self.cpu.reg['SP']:02X}{Style.RESET} ({self.cpu.reg['SP']})")
        print(f"  {Style.BRIGHT_CYAN}├─{Style.RESET} Zero Flag: {Style.BRIGHT_GREEN if self.cpu.zero_flag else Style.DIM}{self.cpu.zero_flag}{Style.RESET}")
        print(f"  {Style.BRIGHT_CYAN}└─{Style.RESET} Carry Flag: {Style.BRIGHT_GREEN if self.cpu.carry_flag else Style.DIM}{self.cpu.carry_flag}{Style.RESET}")
        print()

    def print_registers(self):
        """Print all registers"""
        print(f"\n  {Style.BRIGHT_WHITE}{Style.BOLD}CPU Registers:{Style.RESET}")
        for reg_name in ['A', 'B', 'C', 'D']:
            val = self.cpu.reg[reg_name]
            binary = format(val, '08b')
            print(f"  {Style.BRIGHT_CYAN}{reg_name:3s}{Style.RESET} = {Style.BRIGHT_YELLOW}0x{val:02X}{Style.RESET} ({val:3d}) [{Style.DIM}{binary}{Style.RESET}]")
        
        pc_val = self.cpu.reg['PC']
        sp_val = self.cpu.reg['SP']
        print(f"  {Style.BRIGHT_CYAN}PC {Style.RESET} = {Style.BRIGHT_YELLOW}0x{pc_val:02X}{Style.RESET} ({pc_val:3d})")
        print(f"  {Style.BRIGHT_CYAN}SP {Style.RESET} = {Style.BRIGHT_YELLOW}0x{sp_val:02X}{Style.RESET} ({sp_val:3d})")
        print(f"  {Style.BRIGHT_CYAN}ZF {Style.RESET} = {Style.BRIGHT_GREEN if self.cpu.zero_flag else Style.BRIGHT_RED}{self.cpu.zero_flag}{Style.RESET}")
        print(f"  {Style.BRIGHT_CYAN}CF {Style.RESET} = {Style.BRIGHT_GREEN if self.cpu.carry_flag else Style.BRIGHT_RED}{self.cpu.carry_flag}{Style.RESET}")
        print()

    def read_memory(self, addr: int):
        """Read and display memory"""
        if 0 <= addr < len(self.cpu.memory):
            val = self.cpu.memory[addr]
            print(f"  [{Style.BRIGHT_YELLOW}0x{addr:04X}{Style.RESET}] = {Style.BRIGHT_GREEN}0x{val:02X}{Style.RESET} ({val})")
        else:
            print(f"  {Style.BRIGHT_RED}ERROR: Address out of range{Style.RESET}")

    def write_memory(self, addr: int, value: int):
        """Write to memory"""
        if 0 <= addr < len(self.cpu.memory):
            self.cpu.memory[addr] = value & 0xFF
            print(f"  {Style.BRIGHT_GREEN}✓{Style.RESET} Written {Style.BRIGHT_YELLOW}0x{value:02X}{Style.RESET} to [{Style.BRIGHT_YELLOW}0x{addr:04X}{Style.RESET}]")
        else:
            print(f"  {Style.BRIGHT_RED}ERROR: Address out of range{Style.RESET}")

    def dump_memory(self, start: int, end: int):
        """Dump memory range"""
        print(f"\n  {Style.BRIGHT_WHITE}Memory Dump [{Style.BRIGHT_YELLOW}0x{start:04X}{Style.RESET} - {Style.BRIGHT_YELLOW}0x{end:04X}{Style.RESET}]:{Style.RESET}\n")
        
        for addr in range(start, min(end + 1, len(self.cpu.memory)), 16):
            hex_str = f"{Style.BRIGHT_YELLOW}0x{addr:04X}{Style.RESET}  "
            ascii_str = ""
            
            for i in range(16):
                if addr + i <= end and addr + i < len(self.cpu.memory):
                    byte = self.cpu.memory[addr + i]
                    hex_str += f"{Style.BRIGHT_CYAN}{byte:02X}{Style.RESET} "
                    ascii_str += chr(byte) if 32 <= byte < 127 else f"{Style.DIM}.{Style.RESET}"
                else:
                    hex_str += "   "
                    ascii_str += " "
                
                if i == 7:
                    hex_str += " "
            
            print(f"  {hex_str} {Style.DIM}|{Style.RESET} {ascii_str}")
        print()

    def display_vram(self):
        """Display VRAM contents"""
        print(f"\n  {Style.BRIGHT_WHITE}VRAM Display ({self.cpu.FB_WIDTH}x{self.cpu.FB_HEIGHT}):{Style.RESET}\n")
        
        print(f"  {Style.BRIGHT_CYAN}╔{'═' * (self.cpu.FB_WIDTH * 2)}╗{Style.RESET}")
        for y in range(self.cpu.FB_HEIGHT):
            line = f"  {Style.BRIGHT_CYAN}║{Style.RESET}"
            for x in range(self.cpu.FB_WIDTH):
                val = self.cpu.get_vram_pixel(x, y)
                if val == 0:
                    line += f"{Style.DIM}··{Style.RESET}"
                else:
                    line += f"{Style.BRIGHT_GREEN}{val:02X}{Style.RESET}"
            line += f"{Style.BRIGHT_CYAN}║{Style.RESET}"
            print(line)
        print(f"  {Style.BRIGHT_CYAN}╚{'═' * (self.cpu.FB_WIDTH * 2)}╝{Style.RESET}\n")

    def run_demo(self):
        """Run a demo pattern on VRAM"""
        print(f"  {Style.BRIGHT_GREEN}Running demo pattern...{Style.RESET}\n")
        
        for i in range(10):
            self.cpu.clear_vram()
            for y in range(self.cpu.FB_HEIGHT):
                for x in range(self.cpu.FB_WIDTH):
                    val = ((x + i) * (y + i)) % 16
                    self.cpu.set_vram_pixel(x, y, val)
            
            self.cpu.render(title="DEMO MODE", paused=False)
            time.sleep(0.2)
        
        print(f"\n  {Style.BRIGHT_GREEN}✓ Demo complete{Style.RESET}\n")

    def show_info(self):
        """Display system information"""
        mem_size = len(self.cpu.memory)
        vram_size = self.cpu.VRAM_SIZE
        
        print(f"\n  {Style.BRIGHT_WHITE}{Style.BOLD}System Information:{Style.RESET}")
        print(f"  {Style.BRIGHT_CYAN}├─{Style.RESET} CPU: GEMINI-1 (8-bit)")
        print(f"  {Style.BRIGHT_CYAN}├─{Style.RESET} Memory: {mem_size:,} bytes ({mem_size // 1024}KB)")
        print(f"  {Style.BRIGHT_CYAN}├─{Style.RESET} VRAM: {vram_size} bytes ({self.cpu.FB_WIDTH}x{self.cpu.FB_HEIGHT})")
        print(f"  {Style.BRIGHT_CYAN}├─{Style.RESET} VRAM Start: 0x{self.cpu.VRAM_START:04X}")
        print(f"  {Style.BRIGHT_CYAN}├─{Style.RESET} Stack Top: 0x{self.cpu.STACK_TOP:02X}")
        print(f"  {Style.BRIGHT_CYAN}└─{Style.RESET} Instruction Set: {len(Opcode)} opcodes")
        print()

    def parse_number(self, s: str) -> Optional[int]:
        """Parse a number (hex or decimal)"""
        try:
            if s.upper().startswith('0X'):
                return int(s, 16)
            return int(s)
        except ValueError:
            return None

    def run(self):
        """Run the CLI session"""
        self.print_banner()
        
        try:
            while self.running:
                prompt = f"  {Style.BRIGHT_GREEN}GEMINI>{Style.RESET} "
                print(prompt, end='', flush=True)
                
                # Use standard input for shell instead of the game's InputHandler 
                # to allow full command typing
                cmd_line = sys.stdin.readline().strip().upper()
                if not cmd_line:
                    continue
                
                self.history.append(cmd_line)
                parts = cmd_line.split()
                cmd = parts[0]
                args = parts[1:]
                
                if cmd == 'EXIT' or cmd == 'QUIT':
                    self.running = False
                    print(f"\n  {Style.BRIGHT_CYAN}Exiting shell...{Style.RESET}\n")
                
                elif cmd == 'HELP':
                    self.print_help()
                
                elif cmd == 'STATUS':
                    self.print_status()
                
                elif cmd == 'REGS':
                    self.print_registers()
                
                elif cmd in ['MEM', 'PEEK']:
                    if not args:
                        print(f"  {Style.BRIGHT_RED}Usage: {cmd} <address>{Style.RESET}")
                    else:
                        addr = self.parse_number(args[0])
                        if addr is not None:
                            self.read_memory(addr)
                        else:
                            print(f"  {Style.BRIGHT_RED}ERROR: Invalid address{Style.RESET}")
                
                elif cmd == 'POKE':
                    if len(args) < 2:
                        print(f"  {Style.BRIGHT_RED}Usage: POKE <address> <value>{Style.RESET}")
                    else:
                        addr = self.parse_number(args[0])
                        val = self.parse_number(args[1])
                        if addr is not None and val is not None:
                            self.write_memory(addr, val)
                        else:
                            print(f"  {Style.BRIGHT_RED}ERROR: Invalid address or value{Style.RESET}")
                
                elif cmd == 'DUMP':
                    if len(args) < 2:
                        print(f"  {Style.BRIGHT_RED}Usage: DUMP <start> <end>{Style.RESET}")
                    else:
                        start = self.parse_number(args[0])
                        end = self.parse_number(args[1])
                        if start is not None and end is not None:
                            self.dump_memory(start, end)
                        else:
                            print(f"  {Style.BRIGHT_RED}ERROR: Invalid addresses{Style.RESET}")
                
                elif cmd == 'FILL':
                    if len(args) < 3:
                        print(f"  {Style.BRIGHT_RED}Usage: FILL <start> <end> <value>{Style.RESET}")
                    else:
                        start = self.parse_number(args[0])
                        end = self.parse_number(args[1])
                        val = self.parse_number(args[2])
                        if start is not None and end is not None and val is not None:
                            for addr in range(start, min(end + 1, len(self.cpu.memory))):
                                self.cpu.memory[addr] = val & 0xFF
                            print(f"  {Style.BRIGHT_GREEN}✓{Style.RESET} Filled memory range with {Style.BRIGHT_YELLOW}0x{val:02X}{Style.RESET}")
                        else:
                            print(f"  {Style.BRIGHT_RED}ERROR: Invalid parameters{Style.RESET}")
                
                elif cmd == 'VRAM':
                    self.display_vram()
                
                elif cmd == 'RESET':
                    self.cpu.reg = {'A': 0, 'B': 0, 'C': 0, 'D': 0, 'PC': 0, 'SP': self.cpu.STACK_TOP}
                    self.cpu.zero_flag = False
                    self.cpu.carry_flag = False
                    self.cpu.running = True
                    print(f"  {Style.BRIGHT_GREEN}✓ CPU reset{Style.RESET}")
                
                elif cmd == 'RUN':
                    start_addr = 0
                    if args:
                        addr = self.parse_number(args[0])
                        if addr is not None:
                            start_addr = addr
                    
                    self.cpu.reg['PC'] = start_addr
                    self.cpu.running = True
                    print(f"  {Style.BRIGHT_GREEN}Running from address 0x{start_addr:04X}...{Style.RESET}")
                    
                    steps = 0
                    while self.cpu.running and steps < 1000:
                        self.cpu.step()
                        steps += 1
                    
                    print(f"  {Style.BRIGHT_GREEN}✓ Executed {steps} instructions{Style.RESET}")
                
                elif cmd == 'STEP':
                    n = 1
                    if args:
                        n_val = self.parse_number(args[0])
                        if n_val is not None:
                            n = n_val
                    
                    for _ in range(n):
                        if self.cpu.running:
                            self.cpu.step()
                    
                    print(f"  {Style.BRIGHT_GREEN}✓ Stepped {n} instruction(s){Style.RESET}")
                    self.print_status()
                
                elif cmd == 'DEMO':
                    self.run_demo()
                
                elif cmd == 'INFO':
                    self.show_info()
                
                elif cmd == 'HISTORY':
                    print(f"\n  {Style.BRIGHT_WHITE}Command History:{Style.RESET}\n")
                    for i, h in enumerate(self.history[-20:], 1):
                        print(f"  {Style.DIM}{i:3d}.{Style.RESET} {h}")
                    print()
                
                elif cmd == 'CLEAR':
                    print("\033[2J\033[H")
                    self.print_banner()
                
                elif cmd == 'VER':
                    print(f"\n  {Style.BRIGHT_YELLOW}GEMINI-1 MONITOR v2.0.0{Style.RESET}")
                    print(f"  {Style.DIM}(C) 1983 GEMINI CORPORATION{Style.RESET}")
                    print(f"  {Style.DIM}Enhanced Edition - 2024{Style.RESET}\n")
                
                else:
                    print(f"  {Style.BRIGHT_RED}Unknown command: {cmd}{Style.RESET}")
                    print(f"  {Style.DIM}Type 'HELP' for available commands{Style.RESET}")
                
                print()
        except KeyboardInterrupt:
            print(f"\n  {Style.BRIGHT_CYAN}Exiting shell...{Style.RESET}\n")

def show_game_menu(high_score_manager: HighScoreManager) -> Optional[int]:
    """Show game selection menu with enhanced visuals"""
    games = [
        ("Snake", "Classic snake game - eat and grow!", Style.GREEN, "🐍"),
        ("Pong", "Keep the ball in play!", Style.CYAN, "🔵"),
        ("Breakout", "Break all the bricks!", Style.RED, "🧱"),
        ("Racing", "Dodge obstacles on the road!", Style.MAGENTA, "🏎️"),
        ("Pac-Man", "Eat all dots, avoid the ghosts!", Style.YELLOW, "😮"),
        ("CLI", "System Monitor", Style.DIM, "💻")
    ]

    print("\033[2J\033[H")
    banner = Style.gradient_text(
        " GEMINI-1  ARCADE ",
        [Style.BRIGHT_MAGENTA, Style.BRIGHT_BLUE, Style.BRIGHT_CYAN, Style.BRIGHT_GREEN, Style.BRIGHT_YELLOW],
    )
    print(f"      {Style.BRIGHT_BLACK}{'▄' * 38}{Style.RESET}")
    print(f"      {Style.BRIGHT_BLACK}▌{Style.RESET}{banner:<36}{Style.BRIGHT_BLACK}▐{Style.RESET}")
    print(f"      {Style.BRIGHT_BLACK}{'▀' * 38}{Style.RESET}")
    print(f"      {Style.DIM}Select a game to boot:{Style.RESET}\n")

    for i, (name, desc, color, icon) in enumerate(games, 1):
        high_score = high_score_manager.get_high_score(name)

        if name != "CLI":
            entry = f"{Style.BRIGHT_YELLOW}[{i}]{Style.RESET} {color}{icon}{Style.RESET} {Style.BRIGHT_WHITE}{name:<10}{Style.RESET}  High: {Style.BRIGHT_GREEN}{high_score:>5}{Style.RESET}"
        else:
            entry = f"{Style.BRIGHT_YELLOW}[{i}]{Style.RESET} {color}{icon}{Style.RESET} {Style.BRIGHT_WHITE}{name:<10}{Style.RESET}  {Style.DIM}(System Monitor){Style.RESET}"

        print(f"      {entry}")

        print(f"          {Style.DIM}{desc}{Style.RESET}")
        print()

    print(f"      {Style.BRIGHT_YELLOW}[Q]{Style.RESET} {Style.BRIGHT_WHITE}Quit{Style.RESET}")
    print()

    print(f"{Style.BRIGHT_WHITE}  > {Style.BRIGHT_WHITE}Select option (1-6) or Q to quit:{Style.RESET} ", end='', flush=True)

    try:
        with InputHandler() as handler:
            while True:
                key = handler.get_input()
                if key:
                    if key in ['1', '2', '3', '4', '5', '6']:
                        return int(key) - 1
                    elif key == 'q':
                        return None
                time.sleep(0.01)
    except KeyboardInterrupt:
        return None


def run_game(game: Game):
    """Run a game with enhanced visuals"""
    print("\033[2J\033[H")

    loading_chars = ["/", "-", "\\", "|"]
    game_name = game.get_name()

    for i in range(15):
        char = loading_chars[i % len(loading_chars)]
        color = [Style.CYAN, Style.GREEN, Style.YELLOW, Style.MAGENTA][i % 4]
        print(f"\033[H  +{Style.BRIGHT_BLACK}─{'─' * 28}─+{Style.RESET}")
        print(f"  {Style.BRIGHT_BLACK}│{Style.RESET}  {color}{Style.BOLD}{game_name:^26}{Style.RESET}  {Style.BRIGHT_BLACK}│{Style.RESET}")
        print(f"  {Style.BRIGHT_BLACK}│{Style.RESET}      {color}{char} LOADING...{Style.RESET}            {Style.BRIGHT_BLACK}│{Style.RESET}")
        print(f"  +{Style.BRIGHT_BLACK}─{'─' * 28}─+{Style.RESET}")
        time.sleep(0.08)

    last_update = time.time()
    paused = False

    try:
        with InputHandler() as input_handler:
            while game.cpu.running and not game.game_over:
                info_str = ""
                if isinstance(game, BreakoutGame):
                    lives_display = f"{Style.RED}{'●' * game.lives}{Style.DIM}{'○' * (3 - game.lives)}{Style.RESET}"
                    info_str = f"Lives: {lives_display}"
                elif isinstance(game, PacManGame):
                    power = f"{Style.BRIGHT_YELLOW}{Style.BLINK}POWER!{Style.RESET}" if game.power_mode > 0 else ""
                    info_str = f"Lives: {game.lives} | Dots: {game.dots_remaining}/{game.total_dots} {power}"
                elif isinstance(game, SnakeGame):
                    info_str = f"Speed: {int(1 / game.game_speed * 10)}"

                game.cpu.render(title=game.get_name(), paused=paused, info=info_str)

                key = input_handler.get_input()
                if key:
                    if key in ('q', '0'):
                        game.cpu.running = False
                    elif key in ('r', '9'):
                        game.reset()
                        paused = False
                    elif key == 'p':
                        paused = not paused
                    elif not paused:
                        game.handle_input(key)

                if not paused:
                    current_time = time.time()
                    if current_time - last_update >= game.game_speed:
                        game.update()
                        last_update = current_time

                time.sleep(0.01)

    except KeyboardInterrupt:
        pass

    if game.game_over:
        time.sleep(0.5)
        print("\033[2J\033[H")
        high_score = game.high_score_manager.get_high_score(game.get_name())
        is_new_record = game.score == high_score and game.score > 0

        top_color = Style.BRIGHT_RED if is_new_record else Style.BRIGHT_YELLOW

        box_width = 36
        print()
        print(f"      +{Style.BRIGHT_BLACK}─{'─' * (box_width - 2)}─+{Style.RESET}")
        print(f"      {Style.BRIGHT_BLACK}│{Style.RESET}                                    {Style.BRIGHT_BLACK}│{Style.RESET}")
        print(f"      {Style.BRIGHT_BLACK}│{Style.RESET}  {top_color}{Style.BOLD}*** GAME OVER ***{Style.RESET}                 {Style.BRIGHT_BLACK}│{Style.RESET}")
        print(f"      {Style.BRIGHT_BLACK}│{Style.RESET}                                    {Style.BRIGHT_BLACK}│{Style.RESET}")
        print(f"      {Style.BRIGHT_BLACK}│{Style.RESET}  {Style.DIM}FINAL SCORE:{Style.RESET}                      {Style.BRIGHT_BLACK}│{Style.RESET}")

        score_str = f"{game.score:,}"
        score_padding = (box_width - 4 - len(score_str)) // 2
        print(f"      {Style.BRIGHT_BLACK}│{Style.RESET}{' ' * score_padding}{Style.BRIGHT_GREEN}{Style.BOLD}{score_str}{Style.RESET}{' ' * (box_width - 4 - score_padding - len(score_str))}    {Style.BRIGHT_BLACK}│{Style.RESET}")
        print(f"      {Style.BRIGHT_BLACK}│{Style.RESET}                                    {Style.BRIGHT_BLACK}│{Style.RESET}")
        print(f"      {Style.BRIGHT_BLACK}│{Style.RESET}  {Style.DIM}HIGH SCORE:{Style.RESET}                       {Style.BRIGHT_BLACK}│{Style.RESET}")

        high_str = f"{high_score:,}"
        high_padding = (box_width - 4 - len(high_str)) // 2
        print(f"      {Style.BRIGHT_BLACK}│{Style.RESET}{' ' * high_padding}{Style.BRIGHT_CYAN}{Style.BOLD}{high_str}{Style.RESET}{' ' * (box_width - 4 - high_padding - len(high_str))}    {Style.BRIGHT_BLACK}│{Style.RESET}")

        if is_new_record:
            print(f"      {Style.BRIGHT_BLACK}│{Style.RESET}                                    {Style.BRIGHT_BLACK}│{Style.RESET}")
            print(f"      {Style.BRIGHT_BLACK}│{Style.RESET}      {Style.BRIGHT_YELLOW}{Style.BLINK}*** NEW HIGH SCORE ***{Style.RESET}        {Style.BRIGHT_BLACK}│{Style.RESET}")

        print(f"      {Style.BRIGHT_BLACK}│{Style.RESET}                                    {Style.BRIGHT_BLACK}│{Style.RESET}")
        print(f"      +{Style.BRIGHT_BLACK}─{'─' * (box_width - 2)}─+{Style.RESET}")

        print()
        print(f"      {Style.DIM}Press any key to continue...{Style.RESET}")

        try:
            with InputHandler() as handler:
                while True:
                    if handler.get_input():
                        break
                    time.sleep(0.01)
        except KeyboardInterrupt:
            pass


def show_boot_animation(cpu: GeminiCPU):
    """Show enhanced boot animation"""
    print("\033[2J\033[H")

    boot_colors = [
        Style.BRIGHT_RED, Style.BRIGHT_YELLOW, Style.GREEN,
        Style.CYAN, Style.BRIGHT_BLUE, Style.MAGENTA
    ]

    print()
    print(f"      {Style.BRIGHT_CYAN}{Style.BOLD}G E M I N I - 1   A R C A D E{Style.RESET}")
    print()
    print(f"      {Style.DIM}{'─' * 40}{Style.RESET}")

    boot_messages = [
        (Style.BRIGHT_WHITE, "INITIALIZING SYSTEM...", 0.04),
        (Style.BRIGHT_CYAN, "CHECKING ROM... OK", 0.02),
        (Style.BRIGHT_GREEN, "CHECKING RAM... 64KB OK", 0.02),
        (Style.BRIGHT_YELLOW, "INITIALIZING VRAM... 16x16", 0.02),
        (Style.BRIGHT_MAGENTA, "LOADING I/O DRIVERS... OK", 0.02),
        (Style.BRIGHT_RED, "LOADING SOUND SUBSYSTEM... OK", 0.02),
        (Style.BRIGHT_GREEN, "SYSTEM READY!", 0.1),
    ]

    for color, msg, delay in boot_messages:
        print(f"      {color}> {msg}{Style.RESET}")
        time.sleep(delay)

    print(f"      {Style.DIM}{'─' * 40}{Style.RESET}")
    time.sleep(0.3)

    print()
    print(f"      +{Style.BRIGHT_BLACK}─{'─' * 36}─+{Style.RESET}")
    print(f"      {Style.BRIGHT_BLACK}│{Style.RESET}                                    {Style.BRIGHT_BLACK}│{Style.RESET}")
    print(f"      {Style.BRIGHT_BLACK}│{Style.RESET}      LOADING ARCADE...            {Style.BRIGHT_BLACK}│{Style.RESET}")
    print(f"      {Style.BRIGHT_BLACK}│{Style.RESET}                                    {Style.BRIGHT_BLACK}│{Style.RESET}")

    boot_progress = ["░░░░░░░░░", "▒▒░░░░░░░", "▒▒▒░░░░░░", "▒▒▒▒░░░░░", "▒▒▒▒▒░░░░", "▒▒▒▒▒▒░░░",
                     "▒▒▒▒▒▒▒░░", "▒▒▒▒▒▒▒▒░", "▒▒▒▒▒▒▒▒▒"]
    for i, prog in enumerate(boot_progress):
        print(f"\r      {Style.BRIGHT_BLACK}│{Style.RESET}      {Style.BRIGHT_GREEN}{prog}{Style.RESET} LOADING...       {Style.BRIGHT_BLACK}│{Style.RESET}", end='', flush=True)
        time.sleep(0.05)

    print(f"\r      {Style.BRIGHT_BLACK}│{Style.RESET}      {Style.BRIGHT_GREEN}▒▒▒▒▒▒▒▒▒▒{Style.RESET} COMPLETE!       {Style.BRIGHT_BLACK}│{Style.RESET}")
    print(f"      +{Style.BRIGHT_BLACK}─{'─' * 36}─+{Style.RESET}")

    print()
    print(f"      {Style.BRIGHT_CYAN}{Style.BOLD}PRESS ANY KEY TO ENTER{Style.RESET}")
    print(f"      {Style.DIM}(or wait 3 seconds...){Style.RESET}", end='', flush=True)

    try:
        import select
        start = time.time()
        while time.time() - start < 3:
            if select.select([sys.stdin], [], [], 0.1)[0]:
                sys.stdin.read(1)
                break
    except:
        pass

    time.sleep(0.5)

def main():
    """Main program with enhanced styling"""
    if not sys.stdin.isatty() and os.name != 'nt':
        print(f"{Style.RED}{Style.BOLD}Error:{Style.RESET} Not running in an interactive terminal.")
        print("This program requires a terminal for keyboard input.")
        return

    high_score_manager = HighScoreManager()
    config = GameConfig()

    temp_cpu = GeminiCPU(framebuffer_width=config.width,
                         framebuffer_height=config.height)
    show_boot_animation(temp_cpu)

    try:
        while True:
            choice = show_game_menu(high_score_manager)

            if choice is None:
                print("\033[2J\033[H")

                print()
                print(f"  +{Style.BRIGHT_BLACK}─{'─' * 42}─+{Style.RESET}")
                print(f"  {Style.BRIGHT_BLACK}│{Style.RESET}                                            {Style.BRIGHT_BLACK}│{Style.RESET}")
                print(f"  {Style.BRIGHT_BLACK}│{Style.RESET}        {Style.BRIGHT_WHITE}{Style.BOLD}  THANK YOU FOR PLAYING!{Style.RESET}            {Style.BRIGHT_BLACK}│{Style.RESET}")
                print(f"  {Style.BRIGHT_BLACK}│{Style.RESET}                                            {Style.BRIGHT_BLACK}│{Style.RESET}")
                print(f"  {Style.BRIGHT_BLACK}│{Style.RESET}             {Style.BRIGHT_CYAN}GEMINI-1 ARCADE{Style.RESET}                {Style.BRIGHT_BLACK}│{Style.RESET}")
                print(f"  {Style.BRIGHT_BLACK}│{Style.RESET}                                            {Style.BRIGHT_BLACK}│{Style.RESET}")
                print(f"  {Style.BRIGHT_BLACK}│{Style.RESET}       {Style.BRIGHT_YELLOW}{Style.BLINK}*** *** *** *** *** *** *** ***{Style.RESET}      {Style.BRIGHT_BLACK}│{Style.RESET}")
                print(f"  {Style.BRIGHT_BLACK}│{Style.RESET}                                            {Style.BRIGHT_BLACK}│{Style.RESET}")
                print(f"  +{Style.BRIGHT_BLACK}─{'─' * 42}─+{Style.RESET}")
                print()

                colors = [Style.RED, Style.ORANGE, Style.YELLOW, Style.GREEN, Style.CYAN, Style.BLUE, Style.MAGENTA]
                goodbye = "SEE YOU NEXT TIME!"
                print("  ")
                for i, char in enumerate(goodbye):
                    color = colors[i % len(colors)]
                    print(f"{color}{char}{Style.RESET}", end='', flush=True)
                    time.sleep(0.05)
                print()
                print()
                break

            cpu = GeminiCPU(framebuffer_width=config.width,
                           framebuffer_height=config.height)

            if choice == 5:
                shell = GEMINIShell(cpu)
                shell.run()
                continue

            games = [
                SnakeGame(cpu, high_score_manager),
                PongGame(cpu, high_score_manager),
                BreakoutGame(cpu, high_score_manager),
                RacingGame(cpu, high_score_manager),
                PacManGame(cpu, high_score_manager)
            ]

            run_game(games[choice])

    except KeyboardInterrupt:
        print(f"\n\n{Style.BRIGHT_YELLOW}Game interrupted. Bye!{Style.RESET}")
    except Exception as e:
        print(f"\n{Style.RED}{Style.BOLD}Error:{Style.RESET} {e}")


if __name__ == "__main__":
    main()
