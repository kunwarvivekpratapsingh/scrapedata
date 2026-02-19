import type { Config } from 'tailwindcss'

export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        // Catppuccin Mocha palette (code blocks)
        ctp: {
          base:    '#1e1e2e',
          mantle:  '#181825',
          crust:   '#11111b',
          surface0:'#313244',
          surface1:'#45475a',
          surface2:'#585b70',
          overlay0:'#6c7086',
          overlay1:'#7f849c',
          overlay2:'#9399b2',
          subtext0:'#a6adc8',
          subtext1:'#bac2de',
          text:    '#cdd6f4',
          lavender:'#b4befe',
          blue:    '#89b4fa',
          sapphire:'#74c7ec',
          sky:     '#89dceb',
          teal:    '#94e2d5',
          green:   '#a6e3a1',
          yellow:  '#f9e2af',
          peach:   '#fab387',
          maroon:  '#eba0ac',
          red:     '#f38ba8',
          mauve:   '#cba6f7',
          pink:    '#f5c2e7',
          flamingo:'#f2cdcd',
          rosewater:'#f5e0dc',
        },
        // Layer colors matching generate_report.py
        layer: {
          0: '#3b82f6',
          1: '#0d9488',
          2: '#7c3aed',
          3: '#d97706',
          4: '#dc2626',
        },
      },
      fontFamily: {
        mono: ['JetBrains Mono', 'Fira Code', 'Cascadia Code', 'monospace'],
      },
    },
  },
  plugins: [],
} satisfies Config
