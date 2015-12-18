# Filename: core.py
# Creation Date: Thu 08 Oct 2015
# Last Modified: Fri 20 Nov 2015 12:05:52 AM MST
# Author: Brett Fedack


import curses
import curses.ascii as ascii
import math
import os
import re
import weakref
from datetime import datetime
from . import signals
from .theme import Theme


os.environ['ESCDELAY'] = '25' # Reduces delay after pressing escape key


def key_from_char(n):
    '''
    Converts given numeric representation of a keyboard key to a string

    Parameters:
        n (int): Numeric representation of keyboard key

    Returns:
        str: String representation of keyboard key
    '''
    # Get the keyname.
    key = curses.keyname(n).decode('utf-8')

    # Remove 'KEY_' prefix.
    key = re.sub(r'^KEY_', '',  key)

    # Remove parenthesis in function keys, such as "F(1)".
    key = re.sub(r'^F\(([0-9])\)$', r'F\1', key)

    return key


class UI():
    '''
    Curses-based user interface framework class

    Attributes:
        _error_log (list<Exception>): History of runtime errors
        _focus_trace (list<weakref<Widget>>): Trace of input focus
        _is_running (bool): Flag controlling run state of this UI
        _root (Widget): Root node of widget tree
    '''
    @property
    def root(self):
        ''' Getter for "root" property '''
        return self._root


    def __init__(self, signal_router = None):
        '''
        Parameters:
            signal_router (SignalRouter): Communication hub for this component
                (Optional)
        '''
        # Initialize curses library.
        curses.initscr()
        curses.noecho()          # Hidden input
        curses.curs_set(0)       # Hidden cursor
        curses.cbreak()          # Non-buffered input
        if curses.has_colors():  # Color enabled
            curses.start_color()

        # Setup signal handling.
        signal_router.register('UI_EXIT', self._exit)

        # Initialize attributes.
        self._error_log = []
        self._focus_trace = []
        self._is_running = True
        self._root = Widget(label = 'root', signal_router = signal_router)


    def __del__(self):
        # Deinitialize curses library, and display any errors.
        if not curses.isendwin():
            curses.endwin()
        for e in self._error_log:
            raise e


    def run(self):
        ''' Executes user interface and logs runtime errors '''
        try:
            self._run()
        except Exception as e:
            self._error_log.append(e)


    def _backtrace(self):
        ''' Transfers input focus to the previously focused widget '''
        focus_trace = self._focus_trace

        # Transfer focus upwards.
        focus_trace.pop()
        if focus_trace:
            Widget.input_focus = focus_trace[-1]()


    def _transfer_down(self, new_focus):
        ''' Transfers input focus to a descendant of the current focus

            Parameters:
                new_focus (Widget): New subject of input focus
        '''
        focus_trace = self._focus_trace

        # Transfer input focus.
        focus_trace.append(weakref.ref(new_focus))
        Widget.input_focus = new_focus

        # Synchronize the focus trace.
        actual_focus = Widget.input_focus
        if actual_focus != new_focus:
            focus_trace[-1] = weakref.ref(actual_focus)


    def _exit(self, **kwargs):
        ''' Terminates this user interface '''
        self._is_running = False


    def _run(self):
        ''' Runs user interface event loop '''
        # Determine entry point.
        descendants = self.root._descendants
        entry_point = descendants[0] if descendants else None
        if not entry_point:
            return

        # Set input focus.
        Widget.input_focus = entry_point

        # Reset focus trace.
        focus_trace = self._focus_trace
        focus_trace.clear()

        # Run until an exit signal is received.
        while self._is_running:

            # Redraw user interface.
            self.root._draw()

            # Synchronize input focus with the focus trace.
            if not focus_trace or focus_trace[-1]() is not Widget.input_focus:
                focus_trace.append(weakref.ref(Widget.input_focus))

            # Get the subject of input focus.
            input_focus = Widget.input_focus

            # Get user input.
            c = input_focus._win.getch()

            # Find neighboring, focusable widgets.
            ancestor = input_focus._ancestor
            siblings = ancestor._descendants if ancestor else None
            descendants = input_focus._descendants

            # Transfer input focus upward.
            if (c == ascii.ESC
                and not input_focus._overrides_esc
                and len(focus_trace) > 1
            ):
                self._backtrace()

            # Transfer input focus laterally.
            elif (c in {ascii.TAB, curses.KEY_BTAB}
                  and not input_focus._overrides_tab
                  and len(siblings) > 1
            ):

                # Determine if lateral navigation is possible.
                if siblings and input_focus in siblings:

                    # Reference previous and next focusable siblings.
                    curr_idx = siblings.index(input_focus)
                    prev = siblings[(curr_idx - 1) % (len(siblings))]
                    next = siblings[(curr_idx + 1) % (len(siblings))]

                    # Transfer input focus to a focusable siblings.
                    new_focus = prev if c == curses.KEY_BTAB else next
                    Widget.input_focus = new_focus
                    focus_trace[-1] = weakref.ref(Widget.input_focus)

            # Transfer input focus downward.
            elif (c in {curses.KEY_ENTER, ascii.LF, ascii.CR}
                  and not input_focus._overrides_enter
                  and descendants
            ):
                self._transfer_down(descendants[0])

            # Transfer input focus directly to a descendant.
            elif (c in input_focus._focus_map
                  and descendants[input_focus._focus_map[c]].audit()
            ):
                self._transfer_down(descendants[input_focus._focus_map[c]])

            # Otherwise, pass user input to the focused widget.
            else:
                ret = input_focus.operate(c)

                # The response should be to continue or end operation.
                if ret not in {'CONTINUE', 'END'}:
                    raise RuntimeError(
                        'Returned {}; expected value in {"CONTINUE", "END"}'.format(ret)
                    )

                # Backtrace input focus if operation has come to an end.
                elif ret == 'END':
                    self._backtrace()


class MetaWidget(type):
    ''' Widget metaclass for defining class properties and static methods '''
    @staticmethod
    def set_input_focus(new_focus, **kwargs):
        '''
        Setter for "input_focus" property

        Parameter:
            new_focus (Widget): Widget to set as new input focus
            kwargs: Adapter for optional signal data
        '''
        # Validate input.
        if not isinstance(new_focus, Widget):
            raise TypeError('Received {}; expected Widget'.format(type(new_focus)))

        # Return early if the given widget cannot receive input focus.
        if not new_focus._is_focusable:
            return

        # Retrieve previous input focus.
        previous_focus = Widget.input_focus

        # Report status of the new input focus.
        new_focus._send_status()

        # Assign new input focus.
        Widget._input_focus = weakref.ref(new_focus)

        # Determine if input focus has changed.
        if previous_focus and previous_focus is not new_focus:

            # Update timestamp of new input focus.
            new_focus.update_timestamp()

            # Provide visual feedback to indicate a change in input focus.
            previous_focus.tag_redraw()
            new_focus.tag_redraw()

            # Call overridable blur and focus methods.
            previous_focus.blur()
            new_focus.focus(**kwargs)

            # Emit a signal containing data from the previous input focus.
            output_is_ready, data = previous_focus.compose()
            if output_is_ready:
                signal = signals.Signal('DATASIG_OUT', data, False)
                previous_focus.bubble(**signal.data)

            # Emit a signal requesting data for the new input focus.
            new_focus.request()


    @property
    def input_focus(cls):
        ''' Getter for "input_focus" property '''

        # Return the weakly referenced widget.
        return Widget._input_focus() if Widget._input_focus else None


    @input_focus.setter
    def input_focus(cls, widget):
        ''' Setter for "input_focus" property '''
        Widget.set_input_focus(widget)


    @property
    def theme(cls):
        ''' Getter for "theme" property '''
        return Widget._theme


class Widget(metaclass = MetaWidget):
    '''
    Curses-based widget base class

    Attributes:
        _input_focus (Widget):
        _theme (Theme):

        _label (str): Identifier for this widget
        _win (curses.window): Encapsulated curses window
        _signal_router (SignalRouter): Communication hub for this widget
        _parent (Widget): Parent node in tree of widgets
        _children (list<window>): Child nodes in tree of widgets
        _ancestor (Widget): Nearest focusable ancestor widget
        _descendants (list<Widget>): Nearest focusable descendant widgets
        _focus_key (int): Input character that transfers focus to this widget
        _focus_map (dict<int:int>): Mapping of focus keys to descendant indices
        _links (list<weakref<Widget>>): Non-descendant nodes that are dependent
            on this widget
        _is_focusable (bool): Flag indicating if this widget can gain input
            focus
        _is_drawable (bool): Flag indicating if this widget can be drawn
        _is_tagged (bool): Flag indicating a pending draw operation
        _is_visible (bool): Flag indicating if the subtree rooted at this
            widget is visible
        _timestamp (datetime): Reference date & time for animation purposes;
            updates automatically when input focus changes
        _overrides_enter (bool): Flag indicating if this widget overrides the
            default downward navigation key
        _overrides_esc (bool): Flag indicating if this widget overrides the
            default backtrace navigation key
        _overrides_tab (bool): Flag indicating if this widget overrides the
            default lateral navigation key

    Preconditions:
        Curses library shall be intialized.
    '''
    __metaclass__ = MetaWidget


    _input_focus = None


    _theme = Theme()


    @property
    def input_focus(self):
        ''' Getter for "input_focus" property '''

        # Return the weakly referenced widget.
        return Widget._input_focus() if Widget._input_focus else None


    @input_focus.setter
    def input_focus(self, widget):
        ''' Setter for "input_focus" property '''
        self.set_input_focus(widget)


    @property
    def theme(self):
        ''' Getter for "theme" property '''
        return Widget._theme


    @property
    def label(self):
        ''' Getter for "label" property '''
        return self._label


    def __init__(self, label, parent = None, focus_key = None, signal_router = None):
        '''
        Parameters:
            label (str): Identifier for this widget
            parent (Widget): Parent node in tree of widgets (Optional)
            focus_key (str): Key that initiates focus (Optional)
            signal_router (SignalRouter): Signal router to use for this widget
                (Optional)
        '''
        # Assign given label.
        self._label = label

        # Insert this node into the tree of widgets.
        self._parent = parent
        if parent:
            self._parent._children.append(self)
        self._children = []
        self._descendants = []
        self._focus_map = dict()

        # Indicate that this widget can receive input focus.
        self._is_focusable = True

        # Find closest ancestor that can receive input focus.
        ancestor = parent
        while (ancestor
               and ancestor._parent
               and not ancestor._is_focusable
        ):
            ancestor = ancestor._parent
        self._ancestor = ancestor

        # Communicate this widget's focus key up the ancestor path.
        self._focus_key = focus_key
        if ancestor and focus_key:
            ancestor._focus_map[focus_key] = len(ancestor._descendants)
            ancestor._descendants.append(self)

        # Associate a signal router with this widget.
        self._signal_router = signal_router if signal_router else signals.SignalRouter()

        # Setup signal handlers.
        self.add_signal_handler('DATASIG_IN', self.decompose)
        self.add_signal_handler('DATASIG_FOCUS', self._focus)

        # Encapsulate a curses window in this widget.
        pwin = self._parent._win if parent else curses.newwin(0, 0)
        ph, pw = pwin.getmaxyx()
        py, px = pwin.getbegyx()
        win = curses.newwin(ph, pw, py, px)
        win.keypad(1)
        win.nodelay(1)
        self._win = win

        # Enable rendering of the subtree rooted at this widget.
        self._links = []
        self._is_drawable = True
        self._is_tagged = True
        self._is_visible = True

        # Initialize timestamp
        self.update_timestamp()

        # Disable overrides by default.
        self._overrides_enter = False
        self._overrides_esc = False
        self._overrides_tab = False


    def override(enter = False, esc = False, tab = False):
        '''
        Overrides the default behavior of navigation keys

        Parameters:
            enter (bool): Flag indicating if default downward navigation key
                should be overriden (Optional)
            esc (bool): Flag indicating if default backtrace navigation key
                should be overriden (Optional)
            tab (bool): Flag indicating if default lateral navigation key
                should be overriden (Optional)
        '''
        self._overrides_enter = enter
        self._overrides_esc = esc
        self._overrides_tab = tab


    def update_timestamp(self):
        ''' Updates timestamp to current date & time '''
        self._timestamp = datetime.now()


    def get_time(self):
        ''' Calculates elapsed time (sec) since this widget received focus. '''
        return (datetime.now() - self._timestamp).total_seconds()


    def get_position(self):
        '''
        Gets (x, y) coordinates of this widget relative to its parent.

        Returns:
            2-tuple: x (int), y (int)
        '''
        sy, sx = self._win.getbegyx()
        py, px = self._parent._win.getbegyx() if self._parent else (0, 0)
        return sx - px, sy - py


    def get_size(self):
        '''
        Gets the width and height of this widget

        Returns:
            2-tuple: width (int), height (int)
        '''
        height, width = self._win.getmaxyx()
        return width, height


    def offset(self, x = 0, y = 0):
        '''
        Moves this widget relative to its current position

        Parameters:
            x (int): Relative x-coordinate (Optional)
            y (int): Relative y-coordinate (Optional)

        Returns:
            Widget: Alias to this widget
        '''
        # Determine the bounds of both this widget and its parent.
        p = self._parent._win if self._parent else curses.newwin(0, 0)
        py, px = p.getbegyx()
        ph, pw = p.getmaxyx()
        s = self._win
        sy, sx = s.getbegyx()
        sh, sw = s.getmaxyx()

        # Constrain given offsets within the parent's bounds.
        x = min(max(x + sx, px), px + pw - sw) - sx
        y = min(max(y + sy, py), py + ph - sh) - sy

        # Offset any linked nodes.
        for ref in self._links:
            ref().offset(x, y)

        # Recursively offset the tree of widgets rooted at this node.
        self._offset_tree(x, y)

        return self


    def move(self, x = None, y = None):
        '''
        Moves this widget within the bounds of its parent/screen

        Parameters:
            x (int): x-coordinate (Optional)
            y (int): y-coordinate (Optional)

        Returns:
            Widget: Alias to this widget
        '''
        # Determine the coordinates of this widget and its parent.
        p = self._parent._win if self._parent else curses.newwin(0, 0)
        py, px = p.getbegyx()
        s = self._win
        sy, sx = s.getbegyx()

        # Express coordinates as offsets from the current position.
        x = 0 if x is None else x - (sx - px)
        y = 0 if y is None else y - (sy - py)

        # Offset this widget.
        self.offset(x, y)

        return self


    def resize(self, width = None, height = None):
        '''
        Resizes this widget within the bounds of its parent/screen

        Parameters:
            width (int): Width in columns (Optional)
            height (int): Height in rows (Optional)

        Returns:
            Widget: Alias to this widget
        '''
        # Determine the bounds of both this widget and its parent.
        p = self._parent._win if self._parent else curses.newwin(0, 0)
        py, px = p.getbegyx()
        ph, pw = p.getmaxyx()
        s = self._win
        sy, sx = s.getbegyx()
        sh, sw = s.getmaxyx()

        # Constrain the given dimensions within the parent's bounds.
        width = sw if width is None else min(max(1, width), px + pw - sx)
        height = sh if height is None else min(max(1, height), py + ph - sy)

        # Resize this widget.
        self._win.resize(int(height), int(width))

        # Compensate for the effects resizing may have on any children.
        for child in self._children:
            cy, cx = child._win.getbegyx()
            ch, cw = child._win.getmaxyx()
            child.resize(cw, ch)
            child.move(cx - sx, cy - sy)

        return self


    def scale(self, width = 0, height = 0):
        '''
        Resizes this widget relative to its current dimensions

        Parameters:
            width (int): Change in width (Optional)
            height (int): Change in height (Optional)

        Returns:
            Widget: Alias to this widget
        '''
        sw, sh = self.get_size()
        self.resize(max(2, sw + width), max(2, sh + height))
        return self


    def inset(self, factor):
        '''
        Scales this widget inward from its current bounds

        Parameters:
            factor (int): Inset distance in row-heights

        Returns:
            Widget: Alias to this widget
        '''
        self.scale(-4 * factor, -2 * factor)
        self.offset(2 * factor, 1 * factor)
        return self


    def outset(self, factor):
        '''
        Scales this widget outward from its current bounds

        Parameters:
            factor (int): Outset distance in row-heights

        Returns:
            Widget: Alias to this widget
        '''
        self.offset(-2 * factor, -1 * factor)
        self.scale(4 * factor, 2 * factor)
        return self


    def align(self, mode = 'LEFT', cross = False):
        '''
        Aligns this widget with respect to the width or height of its parent

        Parameters:
            mode (str): Alignment mode in {'START', 'CENTER', 'END'}
                (Optional)
            cross (bool): Cross-alignment flag (Optional)

        Returns:
            Widget: Alias to this widget
        '''
        # Get length along this widget's alignment axis.
        sw, sh = self.get_size()
        span_inner = sh if cross else sw

        # Get length along parent's alignment axis.
        p = self._parent._win if self._parent else curses.newwin(0, 0)
        ph, pw = p.getmaxyx()
        span_outer = ph if cross else pw

        # Determine offset along alignment axis.
        if mode == 'START':
            offset = 0
        elif mode == 'CENTER':
            offset = int((span_outer - span_inner) / 2)
        elif mode == 'END':
            offset = span_outer - span_inner

        # Move this widget.
        x, y = self.get_position()
        self.move(0, offset) if cross else self.move(offset, 0)

        return self


    def hide(self):
        ''' Disables visibility of this widget '''
        self._is_visible = False


    def show(self):
        ''' Enables visibility of this widget '''
        self._is_visible = True


    def toggle_visibility(self):
        ''' Toggles visibility of this widget '''
        self.hide() if self._is_visible else self.show()


    def style(self, name):
        '''
        Retrieves a curses style attribute from this widget's color theme

        Parameters:
            name (str): Name of item to style

        Returns:
            curses.attr: Curses style attribute
        '''
        if not self.audit():
            state = 'disabled'
        elif self.input_focus == self:
            state = 'focused'
        else:
            state = 'default'
        return self.theme.query(state, name)


    def add_signal_handler(self, signame, handler):
        '''
        Registers the given signal handler with this widget's signal router

        Parameters:
            signame (str): Signal name
            handler (function): Signal handler
        '''
        self._signal_router.register(signame, handler)


    def bubble(self, **kwargs):
        '''
        Builds signal from given data and emits it to all ancestor widgets.

        Parameters:
            **kwargs: Signal data
        '''
        # Return early if given data does not identify a signal.
        if '_name' not in kwargs:
            return

        # Build a signal from given data.
        signame = kwargs['_name']
        propagate = kwargs['_propagate'] if '_propagate' in kwargs else True
        signal = signals.Signal(signame, kwargs, propagate)

        # Handle the signal with this widget's parent.
        if self._parent:
            handled = self._parent._signal_router.forward(signal)

            # Continue to bubble the signal while it can be handled.
            if not handled or propagate:
                self._parent.bubble(**kwargs)


    def flush(self, **kwargs):
        '''
        Builds signal from given data and emits it to all descendant widgets.

        Parameters:
            **kwargs: Signal data

        Returns:
            bool: True if signal is handled; false otherwise
        '''
        # Return early if given data does not identify a signal.
        if '_name' not in kwargs:
            return

        # Build a signal from given data.
        signame = kwargs['_name']
        propagate = kwargs['_propagate'] if '_propagate' in kwargs else True
        signal = signals.Signal(signame, kwargs, propagate)

        # Handle the given signal with this widget's descendants.
        handled = False
        for child in self._children:

            # Only handle once if the signal cannot propagate.
            if handled and not propagate:
                break;

            # Handle and flush the signal.
            handled = child._signal_router.forward(signal) or handled
            if not handled or propagate:
                handled = child.flush(**kwargs) or handled

        return handled


    def request(self, **kwargs):
        ''' Bubbles a request for input data '''
        signal = signals.Signal('DATASIG_REQ', propagate = False)
        self.bubble(**signal.data)


    def tag_redraw(self):
        ''' Marks this widget to be redrawn during the next draw call '''
        self._is_tagged = True
        for ref in self._links:
            ref().tag_redraw()


    def audit(self):
        '''
        * Abstract method for inserting user-defined code into UI framework *

        Determines if this widget is operable/disabled

        Returns:
            bool: True if operable; false if disabled
        '''
        return True


    def report(self):
        '''
        * Abstract method for inserting user-defined code into UI framework *

        Generates a report based on this widget's state.

        Returns:
            str: String of status data
        '''
        return {'usage': '', 'is_valid': True, 'validation_msg': ''}


    def focus(self, **kwargs):
        '''
        * Abstract method for inserting user-defined code into UI framework *

        Executes when this widget gains focus; receives optional signal data
        '''
        return


    def blur(self):
        '''
        * Abstract method for inserting user-defined code into UI framework *

        Executes when this widget loses focus
        '''
        return


    def compose(self):
        '''
        * Abstract method for inserting user-defined code into UI framework *

        Defines how to build output signal data

        Returns:
            2-tuple: control flag (bool), signal data (dict)
        '''
        return (False, {})


    def decompose(self, **kwargs):
        '''
        * Abstract method for inserting user-defined code into UI framework *

        Defines how to integrate input signal data into this widget
        '''
        return


    def draw(self):
        '''
        * Abstract method for inserting user-defined code into UI framework *

        Defines how to render this widget during a draw call.
        '''
        return


    def operate(self, c = None):
        '''
        * Abstract method for inserting user-defined code into UI framework *

        Defines how this widget handles user input

        Parameters:
            c (int): Character code for user input (Optional)
        '''
        return 'CONTINUE'


    def _focus(self, **kwargs):
        ''' Transfers input focus to this widget in response to a signal '''
        Widget.set_input_focus(self, **kwargs)


    def _draw(self):
        ''' Draws this widget '''
        self._draw_tagged()
        curses.doupdate()


    def _draw_tagged(self):
        ''' Draws all visible, tagged subtrees in this tree of widgets '''
        # Skip hidden trees.
        if self._is_visible:

            # Draw tree if it is tagged.
            if self._is_tagged:
                self._draw_tree()

            # Otherwise, continue search for tagged trees.
            else:
                for child in self._children:
                    child._draw_tagged()


    def _draw_tree(self):
        ''' Draws the tree of widgets rooted at this node '''
        # Preemptively remove draw tag.
        self._is_tagged = False

        # Skip hidden trees.
        if self._is_visible:

            # Draw this widget.
            if self._is_drawable:
                self._win.bkgdset(self.style('fill'));
                self._win.erase()
                self.draw()
                self._win.noutrefresh()

            # Recursively draw each child subtree.
            for child in self._children:
                child._draw_tree()


    def _offset_tree(self, x, y):
        '''
        Moves the tree of widgets rooted at this node

        Parameters:
            x (int): Relative x-coordinate
            y (int): Relative y-coordinate
        '''
        # Move this widget.
        y_abs, x_abs = self._win.getbegyx()
        self._win.mvwin(int(y_abs + y), int(x_abs + x))

        # Recursively move all descendants of this widget.
        for child in self._children:
            child._offset_tree(x, y)


    def _send_status(self):
        ''' Reports status information, such as usage instructions '''
        # Build a usage string from this widget's focus map.
        descendants = self._descendants
        reverse_focus_map = {v: k for k, v in self._focus_map.items()}
        status = ', '.join([
            '{}:{}'.format(
                key_from_char(reverse_focus_map[i]),
                descendants[i]._label
            )
            for i in range(len(descendants))
            if descendants[i]._is_focusable and descendants[i].audit()
        ])

        # Include output from overridable report method in status.
        status = (status + ', ' + self.report()['usage']).strip(', ')

        # Emit a signal containing this widget's status.
        status_signal = signals.Signal('UI_UPDATE_STATUS', {'status': status}, False)
        self.bubble(**status_signal.data)
        self.flush(**status_signal.data)


class ContentWidget(Widget):
    '''
    Extends base widget in order to provide safe and convenient methods for
    adding content without violating encapsulation of the curses window
    '''
    @property
    def content_region(self):
        '''
        Creates a group for the valid content region of this widget

        Returns:
            Group: Valid content region
        '''
        region = Group(self)
        region.inset(1)
        return region


    def __init__(self, label, parent, focus_key = None):
        # Initialize inherited state.
        super().__init__(label = label, parent = parent, focus_key = focus_key)

        # Initialize attributes.
        self._label_ref = None

        # Setup handlers.
        self.add_signal_handler('UI_CLEAR', self.clear)


    def clear(self, **kwargs):
        '''
        * Abstract method for inserting user-defined code into UI framework *

        Defines how to clear content from this widget
        '''
        return


    def draw_border(self,
                    offset_left = 0,
                    offset_right = 0,
                    offset_top = 0,
                    offset_bottom = 0,
                    char_left = None,
                    char_right = None,
                    char_top = None,
                    char_bottom = None,
                    char_top_left = None,
                    char_top_right = None,
                    char_bottom_left = None,
                    char_bottom_right = None,
                    attr = None              ):
        '''
        Adds a border to this widget

        Parameters:
            offset_left (int): Offset from left edge (Optional)
            offset_right (int): Offset from right edge (Optional)
            offset_top (int): Offset from top edge (Optional)
            offset_bottom (int): Offset from bottom edge (Optional)
            char_left (str): Left side character (Optional)
            char_right (str): Right side character (Optional)
            char_top (str): Top side character (Optional)
            char_bottom (str): Bottom side character (Optional)
            char_top_left (str): Top, left corner character (Optional)
            char_top_right (str): Top, right corner character (Optional)
            char_bottom_left (str): Bottom, left corner character (Optional)
            char_bottom_right (str): Bottom, right corner character (Optional)
            attr (int): Curses style attribute (Optional)
        '''
        width, height = self.get_size()
        win = self._win

        attr = self.style('border') if not attr else attr
        win.attron(attr)

        # Constrain offsets to widget bounds.
        offset_left = max(0, min(offset_left, width - 1))
        offset_right = max(0, min(offset_right, width - 1))
        offset_top = max(0, min(offset_top, height - 1))
        offset_bottom = max(0, min(offset_bottom, height - 1))

        # Convert offsets to relative coordinates.
        border_width = width - offset_left - offset_right - 1
        border_height = height - offset_top - offset_bottom - 1
        x_left = offset_left
        x_right = x_left + border_width
        y_top = offset_top
        y_bottom = y_top + border_height

        # Flip coordinates, if necessary.
        if border_width < 0:
            x_left, x_right = x_right, x_left
            border_width *= -1
        if border_height < 0:
            y_top, y_bottom = y_bottom, y_top
            border_height *= -1

        # Define border characters.
        char_left = char_left if char_left else curses.ACS_VLINE
        char_right = char_right if char_right else curses.ACS_VLINE
        char_top = char_top if char_top else curses.ACS_HLINE
        char_bottom = char_bottom if char_bottom else curses.ACS_HLINE
        char_top_left = char_top_left if char_top_left else curses.ACS_ULCORNER
        char_top_right = char_top_right if char_top_right else curses.ACS_URCORNER
        char_bottom_left = char_bottom_left if char_bottom_left else curses.ACS_LLCORNER
        char_bottom_right = char_bottom_right if char_bottom_right else curses.ACS_LRCORNER

        # Add corners.
        win.addch(y_top, x_left, char_top_left)
        win.addch(y_top, x_right, char_top_right)
        win.addch(y_bottom, x_left, char_bottom_left)
        if offset_bottom > 0 or offset_right > 0:
            win.addch(y_bottom, x_right, char_bottom_right)
        else:
            win.insch(y_bottom, x_right, char_bottom_right)

        # Add sides.
        win.vline(y_top + 1, x_left, char_left, border_height - 1)
        win.vline(y_top + 1, x_right, char_right, border_height - 1)
        win.hline(y_top, x_left + 1, char_top, border_width - 1)
        win.hline(y_bottom, x_left + 1, char_bottom, border_width - 1)

        win.attroff(attr)


    def draw_cursor(self, col, row, margin = (0, 0, 0, 0)):
        '''
        Renders cursor by reversing the underlying colors

        Parameters:
            col (int): Column in which to draw cursor
            row (int): Row in which to draw cursor
            margin (sequence<int>): Left, right, top, and bottom widget margins
                (Optional)
        '''
        # Determine this widget's dimensions.
        width, height = self.get_size()
        effective_width = width - margin[0] - margin[1]

        # Return early if cursor is not within the given margins.
        if (row < margin[2] or row + margin[2] > height - margin[3]
            or col < margin[0] or col + margin[1] > width - margin[2]
        ):
            return

        # Draw the cursor.
        self._win.chgat(row, col, 1, self.style('cursor'))


    def draw_text(self, text, row = 0, padding = (0, 0), margin = (0, 0, 0, 0),
                  hint = None, fit = 'CLIP_RIGHT', expand = 'NONE',
                  align = 'LEFT', attr = None, accent = ''                     ):
        '''
        Adds text to this widget in a bounds-safe and configurable manner

        Parameters:
            text (str): Text content
            row (int): Row in which to start text (Optional)
            padding (sequence<int>): Left and right whitespace padding of text
                (Optional)
            margin (sequence<int>): Left, right, top, and bottom widget margins
                (Optional)
            hint (int): Character to emphasize first occurrence of, if any, in
                the given text; intended to suggest usage (Optional)
            fit (str): Text fitting option in
                {'AUTO_SCROLL', 'CLIP_LEFT', 'CLIP_RIGHT', 'NO_WRAP', 'WRAP'}
                (Optional)
            expand (str): Expansion option for utilizing extra space after text
                {'NONE', 'LEFT', 'RIGHT', 'AROUND'} (Optional)
            align (str): Text alignment option
                {'LEFT', 'CENTER', 'RIGHT'} (Optional)
            attr (int): Curses style attribute (Optional)

        Returns:
            int: Number of lines of text added
        '''
        line_list = []

        # Explicitly type convert arguments.
        row = int(row)
        text = str(text)

        # Determine this widget's dimensions.
        width, height = self.get_size()
        effective_width = width - padding[0] - padding[1] - margin[0] - margin[1]

        # Return early if either the given row is not between the vertical
        # margins or not enough space is available to fit a single, padded
        # character between the horizontal margins.
        if (row < margin[2]
            or row > height - margin[3] - 1
            or effective_width < 1
        ):
            return 0

        # Scroll text over a single line.
        if fit == 'AUTO_SCROLL':
            line_list = [self._auto_scroll(text, effective_width)[:]]

        # Clip text to be left-aligned on a single line.
        elif fit in {'CLIP_RIGHT', 'NO_WRAP'}:
            line_list = [text[:effective_width]]

            # Indicate clipping with an ellipsis.
            if fit == 'CLIP_RIGHT':
                line = line_list[0]
                if len(text) > len(line_list[0]):
                    line_list = [(line[:-3] + '...')[:len(line)]]

        # Shift text to be right-aligned on a single line.
        elif fit == 'CLIP_LEFT':
            line_list = [text[max(0, len(text) - effective_width):]]

            # Indicate shift with an ellipsis.
            line = line_list[0]
            if len(text) > len(line_list[0]):
                line_list = [('...' + line[3:])[:len(line)]]

        # Break text into multiple lines.
        elif fit == 'WRAP':
            line_num = math.ceil(len(text) / effective_width)
            line_list = [text[i * effective_width:(i + 1) * effective_width] for i in range(0, line_num)]

            # Discard out-of-bound lines.
            line_list = line_list[:height - margin[3] - row]

        # Pad line(s) of text.
        line_list = [
            ' ' * padding[0] + line + ' ' * padding[1]
            for line in line_list
        ]

        # Expand line(s) of text.
        if expand in {'LEFT', 'RIGHT', 'AROUND'}:
            template = ""
            if expand == 'LEFT':
                template = '{:>{}}'
            elif expand == 'RIGHT':
                template = '{:<{}}'
            else:
                template = '{:^{}}'
            line_list = [
                template.format(line, width - margin[0] - margin[1])
                for line in line_list
            ]

        # Add line(s) of text to this widget.
        hinted = False
        win = self._win
        attr = self.style('text') if not attr else attr
        win.attron(attr)
        for i in range(len(line_list)):
            line = line_list[i]

            # Determine offset from left edge of this widget.
            if align == 'CENTER':
                offset = int((width - margin[0] - margin[1] - len(line)) / 2) + margin[0]
            elif align == 'RIGHT':
                offset = width - margin[1] - len(line)
            else:
                offset = margin[0]

            # Add offset line of text.
            if offset + len(line) < width:
                win.addstr(row + i, offset, line)
            else:
                win.addstr(row + i, offset, line[:-1])
                win.insch(row + i, width - 1, ord(line[-1]))

            # Emphasize first occurrence of given character, provided that this
            # has an ancestor that can receive focus.
            if (self._ancestor is Widget.input_focus
                and hint and not hinted
                and chr(hint) in line.lower()
            ):
                idx = line.lower().find(chr(hint))
                win.chgat(row + i, offset + idx, 1, attr | curses.A_UNDERLINE)
                hinted = True
        win.attroff(attr)

        return len(line_list)


    def _auto_scroll(self, text, width, gap = 8, rate = 5, delay = 0.67):
        '''
        Scrolls text on a single line over time

        Parameters:
            text (str): Text to scroll
            width (int): Space within which to scroll
            gap (int): Number of spaces separating ends of text (Optional)
            rate (float): Scroll rate in characters per second (Optional)
            delay (float): Pause duration (sec) before scrolling (Optional)

        Returns:
            str: Scrolled string of text
        '''
        # Return early if text does not exceed scroll bounds.
        if len(text) < width:
            return text

        # Pad text with given number of spaces.
        text += ' ' * gap

        # Determine the interval between complete scrolls.
        period = delay + len(text) / rate

        # Determine the start index.
        period_time = self.get_time() % period
        if period_time < delay:
            start = 0
        else:
            start = int(rate * (period_time - delay))

        # Scroll text to calculated start position.
        text = (text[start:] + text[:start])[:width]

        return text


class DatasigTranslator(Widget):
    '''
    Modifies input, output, focus, and request data signals that pass through
    this node of the widgets tree

    Attributes:
        _translation_map (dict): Source-target translation pairs
    '''
    def __init__(self, parent):
        # Initialize inherited state.
        super().__init__('Translator', parent = parent)

        # Prevent this widget from being drawn.
        self._is_drawable = False

        # Prevent this widget from receiving input focus.
        self._is_focusable = False

        # Initialize translation map.
        self._translation_map = {
            'INPUT': {},
            'OUTPUT': {'DATASIG_OUT': 'DATASIG_OUT'},
            'FOCUS': {},
            'REQUEST': {'DATASIG_REQ': 'DATASIG_REQ'}
        }

        # Setup signal handling.
        self.add_signal_handler('DATASIG_OUT', self._translate_output);
        self.add_signal_handler('DATASIG_REQ', self._translate_request);


    def map_input(self, signame, **kwargs):
        '''
        Adds given terms to the input translation map

        Parameters:
            signame (str): Source signal name
            **kwargs: Source (keyword) to target (argument) translation pairs
        '''
        self.add_signal_handler(signame, self._translate_input)
        self._translation_map['INPUT'].update(kwargs)


    def map_output(self, signame, **kwargs):
        '''
        Adds given terms to the output translation map

        Parameters:
            signame (str): Target signal name
            **kwargs: Source (keyword) to target (argument) translation pairs
        '''
        self._translation_map['OUTPUT']['DATASIG_OUT'] = signame
        self._translation_map['OUTPUT'].update(kwargs)


    def map_focus(self, signame, **kwargs):
        '''
        Adds given terms to the focus translation map

        Parameters:
            signame (str): Source signal name
            **kwargs: Source (keyword) to target (argument) translation pairs
        '''
        self.add_signal_handler(signame, self._translate_focus)
        self._translation_map['FOCUS'].update(kwargs)


    def map_request(self, signame, **kwargs):
        '''
        Adds given terms to the request translation map

        Parameters:
            signame (str): Target signal name
            **kwargs: Source (keyword) to target (argument) translation pairs
        '''
        self._translation_map['REQUEST']['DATASIG_REQ'] = signame
        self._translation_map['REQUEST'].update(kwargs)


    def _translate_data(self, section, data):
        '''
        Translates given data using the specified section of the translation map

        Parameters:
            section (str): Section of translation map in
                {'INPUT', 'OUTPUT', 'FOCUS', 'REQUEST'}
            data (dict): Data to translate

        Returns:
            dict: Translated data
        '''
        ret = {}
        for k, v in data.items():
            if k in self._translation_map[section]:
                k = self._translation_map[section][k]
            ret[k] = v
        return ret


    def _translate_input(self, **kwargs):
        '''
        Translates an input signal and flushes the result

        Parameters:
            **kwargs: Expanded signal data
        '''
        # Translate input signal's name.
        signame = 'DATASIG_IN'

        # Translate data carried by input signal.
        data = self._translate_data('INPUT', kwargs)

        # Emit translated input signal.
        signal = signals.Signal(signame, data, False)
        self.flush(**signal.data)


    def _translate_output(self, **kwargs):
        '''
        Translates an output signal and bubbles the result

        Parameters:
            **kwargs: Expanded signal data
        '''
        # Translate output signal's name.
        signame = self._translation_map['OUTPUT']['DATASIG_OUT']

        # Translate data carried by output signal.
        data = self._translate_data('OUTPUT', kwargs)

        # Emit translated output signal.
        signal = signals.Signal(signame, data, signame != 'DATASIG_OUT')
        self.bubble(**signal.data)


    def _translate_focus(self, **kwargs):
        '''
        Translates a focus signal and flushes the result

        Parameters:
            **kwargs: Expanded signal data
        '''
        # Translate input signal's name.
        signame = 'DATASIG_FOCUS'

        # Translate data carried by focus signal.
        data = self._translate_data('FOCUS', kwargs)

        # Emit translated focus signal.
        signal = signals.Signal(signame, data, False)
        self.flush(**signal.data)


    def _translate_request(self, **kwargs):
        '''
        Translates a request signal and bubbles the result

        Parameters:
            **kwargs: Expanded signal data
        '''
        # Translate output signal's name.
        signame = self._translation_map['REQUEST']['DATASIG_REQ']

        # Translate data carried by request signal.
        data = self._translate_data('REQUEST', kwargs)

        # Emit translated request signal.
        signal = signals.Signal(signame, data, signame != 'DATASIG_REQ')
        self.bubble(**signal.data)


class Form(Widget):
    '''
    Consolidates multiple "DATASIG_OUT" signals

    Attributes:
        _defaults (dict): Default form data
        _data (dict): Collective data from one or more signals
    '''
    def __init__(self, parent, **kwargs):
        # Initialize inherited state.
        super().__init__('Form', parent = parent)

        # Prevent this widget from being drawn.
        self._is_drawable = False

        # Prevent this widget from receiving input focus.
        self._is_focusable = False

        # Setup signal handling.
        self.add_signal_handler('UI_CLEAR_FORM', self._clear)
        self.add_signal_handler('DATASIG_OUT', self._consolidate)
        self.add_signal_handler('UI_SUBMIT', self._submit)

        # Initialize attributes.
        self._defaults = kwargs
        self._data = kwargs.copy()


    def _clear(self, **kwargs):
        ''' Clears content from descendant widgets '''
        # Clear form.
        self._data = self._defaults.copy()

        # Clear form inputs.
        signal = signals.Signal('UI_CLEAR')
        self.flush(**signal.data)


    def _consolidate(self, **kwargs):
        ''' Collects signal data for eventual submission '''
        self._data.update(kwargs)


    def _submit(self, **kwargs):
        ''' Submits consolidated signal data '''
        signal = signals.Signal('DATASIG_OUT', self._data, False)
        self.bubble(**signal.data)


class Group(Widget):
    ''' Container for grouping widgets '''
    def __init__(self, parent, **kwargs):
        # Initialize inherited state.
        super().__init__('Group', parent = parent)

        # Prevent this widget from being drawn.
        self._is_drawable = False

        # Prevent this widget from receiving input focus.
        self._is_focusable = False
