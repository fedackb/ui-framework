# Filename: theme.py
# Creation Date: Thu 08 Oct 2015
# Last Modified: Sat 07 Nov 2015 03:50:28 PM MST
# Author: Brett Fedack


import curses
import math


class Theme():
    '''
    Theme providing state-based mapping of names to curses attributes

    Attributes:
        _colors (dict): Mapping of rgb tuples to color indices
        _color_pairs (dict): Mapping of foreground, background rgb tuples to
            curses color pair objects
        _data (dict): Theme data formatted as follows:
            {
                state: {
                    name: attr
                },
                ...
            }
            state in {'default', 'focused', 'disabled'}
    '''
    def __init__(self):
        # Initialize theme data.
        self._colors = {}
        self._color_pairs = {}
        self._data = {
            'default': {},
            'focused': {},
            'disabled': {},
        }


    def edit(self, state, name, fg, bg, *args):
        '''
        Adds given item to the theme

        Parameters:
            state (str): Theme state
            name (str): Identifier keyed to curses attribute
            fg (3-tuple<float>): Foreground color as normalized rgb values
            bg (3-tuple<float>): Background color as normalized rgb values
            *args: Formatting attributes in
                {'BLINK', 'BOLD', 'REVERSE', 'UNDERLINE'} (Optional)

        Preconditions:
            Curses library shall be intialized.
        '''
        # Return early if given state is invalid.
        if state not in self._data:
            return

        # Process color input.
        color_attr = 0;
        if curses.has_colors() and curses.can_change_color():

            # Translate give colors to curses color items.
            colors = self._colors
            fg = tuple(math.floor(i * 1000) for i in fg)
            bg = tuple(math.floor(i * 1000) for i in bg)
            for rgb in fg, bg:
                if rgb not in colors:
                    color_idx = len(colors) + 16 # 16-color terminal palette
                    curses.init_color(color_idx, *rgb)
                    colors[rgb] = color_idx

            # Associate foreground and background as a curses color pair object.
            color_pairs = self._color_pairs
            pair = (fg, bg)
            if pair not in color_pairs:
                color_pair_idx = len(color_pairs) + 8 # 16-color terminal palette
                curses.init_pair(color_pair_idx, colors[fg], colors[bg])
                color_pairs[pair] = color_pair_idx

            # Get color attribute.
            color_attr = curses.color_pair(color_pairs[pair])

        # Combine formatting attributes into a single curses attribute.
        format_attr = 0
        if 'BLINK' in args:
            format_attr |= curses.A_BLINK
        if 'BOLD' in args:
            format_attr |= curses.A_BOLD
        if 'REVERSE' in args:
            format_attr |= curses.A_REVERSE
        if 'UNDERLINE' in args:
            format_attr |= curses.A_UNDERLINE

        # Insert combined color and formatting attributes into this theme.
        self._data[state][name] = color_attr | format_attr


    def load(self, theme_data):
        '''
        Loads all valid items from given theme data

        Parameters:
            theme_data (dict): Curses attribute theme data
        '''
        for state in theme_data:
            for name in theme_data[state]:
                self.edit(state, name, *theme_data[state][name])


    def query(self, state, name):
        '''
        Retrieves curses attribute from theme without throwing a key error

        Parameters:
            state (str): Theme state
            name (str): Identifier keyed to curses attribute
        '''
        if state in self._data:
            if name in self._data[state]:
                return self._data[state][name]
        return 0
