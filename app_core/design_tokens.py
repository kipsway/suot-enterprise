from dataclasses import dataclass, field
from typing import Dict, Tuple


@dataclass(frozen=True)
class ColorPalette:
    accent: str = "#007AFF"
    accent_hover: str = "#0066D6"
    accent_pressed: str = "#0055B3"
    accent_light: str = "#E3F2FF"

    bg_primary: str = "#FFFFFF"
    bg_secondary: str = "#F2F2F7"
    bg_tertiary: str = "#E5E5EA"
    bg_glass: str = "rgba(255,255,255,0.6)"

    text_primary: str = "#1C1C1E"
    text_secondary: str = "rgba(28,28,30,0.6)"
    text_tertiary: str = "rgba(28,28,30,0.35)"
    text_inverse: str = "#FFFFFF"
    text_link: str = "#007AFF"

    border: str = "rgba(60,60,67,0.12)"
    border_focus: str = "#007AFF"
    border_error: str = "#FF3B30"

    success: str = "#34C759"
    warning: str = "#FF9500"
    error: str = "#FF3B30"
    info: str = "#007AFF"

    surface_raised: str = "#FFFFFF"
    surface_overlay: str = "rgba(0,0,0,0.35)"
    skeleton: str = "#E5E5EA"
    scrollbar: str = "rgba(60,60,67,0.25)"


@dataclass(frozen=True)
class DarkColorPalette:
    accent: str = "#0A84FF"
    accent_hover: str = "#409CFF"
    accent_pressed: str = "#0066D6"
    accent_light: str = "#1A3A5C"

    bg_primary: str = "#000000"
    bg_secondary: str = "#1C1C1E"
    bg_tertiary: str = "#2C2C2E"
    bg_glass: str = "rgba(28,28,30,0.8)"

    text_primary: str = "#FFFFFF"
    text_secondary: str = "rgba(255,255,255,0.6)"
    text_tertiary: str = "rgba(255,255,255,0.35)"
    text_inverse: str = "#000000"
    text_link: str = "#0A84FF"

    border: str = "rgba(255,255,255,0.12)"
    border_focus: str = "#0A84FF"
    border_error: str = "#FF453A"

    success: str = "#30D158"
    warning: str = "#FF9F0A"
    error: str = "#FF453A"
    info: str = "#0A84FF"

    surface_raised: str = "#1C1C1E"
    surface_overlay: str = "rgba(0,0,0,0.55)"
    skeleton: str = "#2C2C2E"
    scrollbar: str = "rgba(255,255,255,0.2)"


@dataclass(frozen=True)
class ShadowTokens:
    small: str = "0 1px 3px rgba(0,0,0,0.08)"
    medium: str = "0 4px 12px rgba(0,0,0,0.1)"
    large: str = "0 8px 24px rgba(0,0,0,0.12)"
    xl: str = "0 16px 48px rgba(0,0,0,0.15)"
    glow_accent: str = "0 0 12px rgba(0,122,255,0.3)"
    glow_error: str = "0 0 12px rgba(255,59,48,0.3)"

    @staticmethod
    def dark(s: str) -> str:
        return s.replace("rgba(0,0,0,", "rgba(0,0,0,")


@dataclass(frozen=True)
class RadiusTokens:
    xs: str = "4px"
    sm: str = "6px"
    md: str = "8px"
    lg: str = "12px"
    xl: str = "16px"
    pill: str = "9999px"


@dataclass(frozen=True)
class FontTokens:
    family: str = "'Segoe UI Variable', 'SF Pro Display', -apple-system, sans-serif"
    mono: str = "'JetBrains Mono', 'Cascadia Code', 'Consolas', monospace"
    size_xs: str = "11px"
    size_sm: str = "12px"
    size_md: str = "13px"
    size_lg: str = "15px"
    size_xl: str = "17px"
    size_2xl: str = "20px"
    size_3xl: str = "26px"
    weight_regular: str = "400"
    weight_semibold: str = "600"
    weight_bold: str = "700"
    line_height_tight: str = "1.2"
    line_height_normal: str = "1.4"
    line_height_relaxed: str = "1.6"


@dataclass(frozen=True)
class SpacingTokens:
    xs: str = "4px"
    sm: str = "8px"
    md: str = "12px"
    lg: str = "16px"
    xl: str = "20px"
    xxl: str = "24px"
    section: str = "32px"


@dataclass(frozen=True)
class AnimationTokens:
    fast_ms: int = 100
    normal_ms: int = 200
    slow_ms: int = 300
    xl_ms: int = 400

    easing_linear: str = "linear"
    easing_out: str = "ease-out"
    easing_in_out: str = "ease-in-out"
    easing_spring: str = "cubic-bezier(0.34, 1.56, 0.64, 1)"
    easing_bounce: str = "cubic-bezier(0.68, -0.55, 0.265, 1.55)"
    easing_smooth: str = "cubic-bezier(0.4, 0, 0.2, 1)"
    easing_decelerate: str = "cubic-bezier(0, 0, 0.2, 1)"
    easing_accelerate: str = "cubic-bezier(0.4, 0, 1, 1)"


@dataclass(frozen=True)
class GlassTokens:
    light_bg: str = "rgba(255,255,255,0.6)"
    light_border: str = "rgba(255,255,255,0.3)"
    light_blur: str = "20px"
    dark_bg: str = "rgba(28,28,30,0.8)"
    dark_border: str = "rgba(255,255,255,0.08)"
    dark_blur: str = "30px"


LIGHT = ColorPalette()
DARK = DarkColorPalette()
SHADOW = ShadowTokens()
RADIUS = RadiusTokens()
FONT = FontTokens()
SPACING = SpacingTokens()
ANIM = AnimationTokens()
GLASS = GlassTokens()


def palette(is_dark: bool) -> ColorPalette:
    return DARK if is_dark else LIGHT
