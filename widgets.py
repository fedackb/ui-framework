# Filename: widgets.py
# Creation Date: Thu 08 Oct 2015
# Last Modified: Thu 17 Dec 2015 11:01:48 AM MST
# Author: Brett Fedack


import math
import curses
import curses.ascii as ascii
import weakref
from . import signals
from .core import Widget, ContentWidget, Group


class Button(ContentWidget):
    '''
    Push button widget

    Attributes:
        _is_pushed (bool): Button state
    '''
    def __init__(self, label, parent, focus_key = None):
        # Initialize inherited state.
        super().__init__(label, parent, focus_key)

        # Initialize size.
        self.fit()

    def report(self):
        return {'usage': 'Enter:Execute'}


    def focus(self, **kwargs):
        # This button has yet to be pushed.
        self._is_pushed = False


    def compose(self):
        # Bubble a data signal if this button was pressed.
        return (self._is_pushed, {})


    def draw(self):
        width = self.get_size()[0]

        # Draw bounding parenthesis.
        self.draw_text('(', attr = self.style('text'))
        self.draw_text(')', margin = (width - 1, 0, 0, 0), attr = self.style('text'))

        # Draw button label within parenthesis.
        self.draw_text(self._label, padding = (1, 1), margin = (1, 1, 0, 0), align = 'CENTER', hint = self._focus_key, attr = self.style('text'))


    def operate(self, c):
        # Push this button.
        if c in {curses.KEY_ENTER, ascii.LF, ascii.CR}:
            self._is_pushed = True
            return 'END'

        return 'CONTINUE'


    def fit(self):
        ''' Fits button to padded label width '''
        self.resize(len(self._label) + 4, 1)


class StatusLine(ContentWidget):
    '''
    Displays usage instructions, feedback messages, and confirmation prompts

    Attributes:
        _error (bool):
        _mode (str): Mode of operation in
            {'PROMPT_CONFIRM', 'DISPLAY_FEEDBACK'}
        _feedback (str): Message containing feedback
        _prompt (str): Confirmation prompt
        _sigconfirm (str): Name of confirmation signal to emit
        _status (str): Status report
    '''
    def __init__(self, label, parent, focus_key = None):
        # Initialize inherited state.
        super().__init__(label, parent, focus_key)

        # Setup signal handling.
        self.add_signal_handler('UI_FEEDBACK', self._display_feedback)
        self.add_signal_handler('UI_PROMPT_CONFIRM', self._prompt_confirm)
        self.add_signal_handler('UI_UPDATE_STATUS', self._update_status)

        # Initialize attributes.
        self._mode = ''
        self._error = ''
        self._feedback = ''
        self._prompt = ''
        self._sigconfirm = ''
        self._status = ''
        self._timer = 0


    def draw(self):
        text = ''
        post_text = ''
        spacer = 3
        margin = [1, 1, 1, 1]
        attr = self.style('status')
        width, height = self.get_size()

        # Format text according to focus state and mode of operation.
        if Widget.input_focus is self:
            if self._mode == 'PROMPT_CONFIRM':
                post_text = 'Enter:OK, Esc:Cancel'
                text = self._prompt
            elif self._mode == 'DISPLAY_FEEDBACK':
                text = ('ERROR' if self._error else 'SUCCESS') + ': ' + self._feedback
                post_text = 'Enter/Esc:Continue'
                attr = self.style('error') if self._error else self.style('success')
            margin[1] += len(post_text) + spacer
        else:
            text = self._status

        # Tag for redraw in order to animate the scroll.
        effective_width = width - margin[0] - margin[1]
        if len(text) > effective_width:
            self.tag_redraw()

        # Draw status line text content.
        self.draw_text(text, row = 1, margin = margin, fit = 'AUTO_SCROLL', attr = attr)
        margin = [width - len(post_text) - 1, 1, 1, 1]
        self.draw_text(post_text, row = 1, margin = margin, attr = attr)

        # Draw border around status line.
        self.draw_border(attr = attr)


    def operate(self, c):
        # Display prompt until user either confirms or cancels.
        if self._mode == 'PROMPT_CONFIRM':

            # Confirm.
            if c in {curses.KEY_ENTER, ascii.LF, ascii.CR}:

                # Emit the requested confirmation signal.
                self.bubble(**self._sigconfirm.data)

                return 'END'

        # Display feedback message until user presses a key.
        elif self._mode == 'DISPLAY_FEEDBACK':
            if c in {curses.KEY_ENTER, ascii.LF, ascii.CR}:
                return 'END'

        return 'CONTINUE'


    def _display_feedback(self, message, error, **kwargs):
        '''
        Prompts the user for confirmation (OK, Cancel)

        Parameters:
            prompt (str): Confirmation request message
            sigconfirm (Signal): Signal to emit upon confirmation
        '''
        self._mode = 'DISPLAY_FEEDBACK'
        self._feedback = message
        self._error = error
        Widget.input_focus = self


    def _prompt_confirm(self, prompt, sigconfirm, **kwargs):
        '''
        Prompts the user for confirmation (OK, Cancel)

        Parameters:
            prompt (str): Confirmation request message
            sigconfirm (Signal): Signal to emit upon confirmation
        '''
        self._mode = 'PROMPT_CONFIRM'
        self._prompt = prompt
        self._sigconfirm = sigconfirm
        Widget.input_focus = self


    def _update_status(self, status, **kwargs):
        ''' Updates status line usage information '''
        self.update_timestamp()
        self._status = status
        self.tag_redraw()


class Tab(ContentWidget):
    '''
    Tabbed container for widgets

    Attributes:
        _tab_list (list<Tab>): List of sibling tabs
    '''
    @property
    def content_region(self):
        '''
        Creates a group for the valid content region of this widget

        Returns:
            Group: Valid content region
        '''
        region = Group(self)
        region.scale(height = -2).offset(y = 2).inset(1)
        return region


    def __init__(self, label, parent, focus_key = None):
        # Initialize inherited state.
        super().__init__(label, parent, focus_key)

        # Initialize attributes.
        self._tab_list = []

        # Update tab list.
        tab_list = [node for node in parent._children if isinstance(node, Tab)]

        # Synchronize sibling tab lists.
        for tab in tab_list:
            tab._tab_list = tab_list

        # Only show the first tab of the list.
        tab_list[0].show()
        for tab in tab_list[1:]:
            tab.hide()


    def focus(self, **kwargs):
        # Hide all sibling tabs.
        for tab in self._tab_list:
            tab.hide()
        self.show()


    def draw(self):
        width, height = self.get_size()
        margin = [2, 1, 1, height - 3]
        margin_left = margin_right = 0

        # Draw sibling tabs.
        for tab in self._tab_list:

            # Determine dimensions of tab label.
            tab_width = len(tab.label) + 4
            margin[1] = width - margin[0] - tab_width

            # Draw border around sibling tab's label.
            if tab is self:
                margin_left = margin[0]
                margin_right = margin[1]
            else:
                self.draw_border(
                    offset_left = margin[0],
                    offset_right = margin[1],
                    offset_bottom = margin[3],
                    attr = self.style('inactive')
                )
            margin[0] += 2

            # Draw sibling tab's label.
            if tab is not self:
                self.draw_text(
                    tab.label, row = 1, margin = margin, hint = tab._focus_key,
                    attr = self.style('inactive')
                )
            margin[0] += tab_width

        # Add border around contained widgets.
        self.draw_border(offset_top = 2)

        # Draw border around this tab.
        margin[0] = margin_left
        margin[1] = margin_right
        self.draw_border(
            offset_left = margin[0],
            offset_right = margin[1],
            offset_bottom = margin[3],
            char_bottom = ord(' '),
            char_bottom_left = curses.ACS_LRCORNER,
            char_bottom_right = curses.ACS_LLCORNER
        )
        margin[0] += 2

        # Draw this tab's label.
        self.draw_text(
            self._label, row = 1, margin = margin, hint = self._focus_key,
            attr = self.style('label')
        )


class VertTab(Tab):
    ''' Tabbed container for widgets (aligned vertically) '''
    @property
    def content_region(self):
        '''
        Creates a widget group for the valid content region of this tab

        Returns:
            Group: Valid content region
        '''
        tab_width = max([len(node.label) for node in self._tab_list]) + 4
        region = Group(self)
        region.scale(width = -1 * (tab_width - 1))
        region.offset(tab_width - 1).inset(1)
        return region


    def draw(self):
        width, height = self.get_size()
        tab_list = self._tab_list

        # Determine width of all tabs.
        tab_width = max([len(node.label) for node in self._tab_list]) + 4

        # Draw sibling tabs.
        tab_offset = 1
        margin = (2, width - tab_width + 2, 1, 1)
        for i in range(len(tab_list)):
            tab = tab_list[i]

            # Draw border around sibling tab's label.
            if tab is self:
                si = i
            else:
                self.draw_border(
                    offset_right = width - tab_width,
                    offset_top = 3 * i + tab_offset,
                    offset_bottom = height - (3 * i + 2 + tab_offset) - 1,
                    attr = self.style('inactive')
                )

            # Draw sibling tab's label.
            if tab is not self:
                self.draw_text(
                    tab.label, row = 3 * i + 1 + tab_offset, margin = margin, hint = tab._focus_key,
                    attr = self.style('inactive')
                )

        # Add border around contained widgets.
        self.draw_border(offset_left = tab_width - 1)

        # Draw border around this tab.
        self.draw_border(
            offset_right = width - tab_width,
            offset_top = 3 * si + tab_offset,
            offset_bottom = height - (3 * si + 2 + tab_offset) - 1,
            char_right = ord(' '),
            char_top_right = curses.ACS_LRCORNER,
            char_bottom_right = curses.ACS_URCORNER
        )

        # Draw this tab's label.
        self.draw_text(
            self._label, row = 3 * si + 1 + tab_offset, margin = margin, hint = self._focus_key,
            attr = self.style('label')
        )


class Text(ContentWidget):
    '''
    Text display widget

    Attributes
        _line_list (list<str>): Lines of text
    '''
    def __init__(self, label, parent, style = 'text'):
        '''
        Parameters:
            style (str): Theme style attribute for text content
        '''
        # Initialize inherited state.
        super().__init__(label, parent)

        # Prevent this widget from receiving input focus.
        self._is_focusable = False

        # Initialize attributes.
        self._style = style
        self._line_list = []


    def draw(self):
        # Draw all lines of text.
        line_list = self._line_list
        for i in range(len(line_list)):
            line = line_list[i]
            self.draw_text(line, row = i, attr = self.style(self._style))


    def add_line(self, line):
        '''
        Adds given line of text to this widget

        Parameters:
            line (str): Line of text
        '''
        self._line_list.append(line)


    def add_raw(self, raw):
        '''
        Adds given raw string, line-by-line, to this widget

        Parameters:
            raw (str): Raw string
        '''
        for line in raw.splitlines():
            self.add_line(line)


class Label(ContentWidget):
    '''
    Widget that is used to display the label of another widget

    Attributes:
        _used_by (weakref<Widget>): Reference to widget that uses this label
        _text (str): Embellished text representation of the label
    '''
    @property
    def used_by(self):
        return self._used_by() if self._used_by else None


    def __init__(self, parent, used_by):
        # Initialize attributes.
        self._used_by = weakref.ref(used_by)
        self._label = used_by._label

        # Initialize inherited state.
        super().__init__(self._label, parent)

        # Prevent this widget from receiving input focus.
        self._is_focusable = False

        # Initialize size.
        self.fit()


    def draw(self):
        # Used referenced style.
        style = self.used_by.style

        # Draw the embellished label.
        self.draw_text(self.label, attr = style('label'), hint = self.used_by._focus_key)


    def embellish(self, prefix = '', suffix = ''):
        '''
        Embellishes the label with leading and trailing text

        Parameters:
            prefix (str): Text to add before label (Optional)
            suffix (str): Text to add after label (Optional)

        Returns:
            Widget: Alias to this widget
        '''
        self._label = prefix + self.used_by._label + suffix
        self.fit()
        return self


    def fit(self):
        '''
        Fits this widget's dimensions to its content

        Returns:
            Widget: Alias to this widget
        '''
        self.resize(len(self._label), 1)
        return self


    def shift(self, multiple):
        '''
        Offsets horizontally by a multiple of this label's width

        Parameters:
            multiple (float): Scalar multiple of label's width

        Returns:
            Widget: Alias to this widget
        '''
        self.offset(x = round(multiple * self.get_size()[0]))
        return self


    def to_center(self, cross = False):
        '''
        Moves this label to the center of the widget that uses it

        Parameters:
            cross (bool): Cross-alignment flag (Optional)

        Returns:
            Widget: Alias to this widget
        '''
        ux, uy = self.used_by.get_position()
        uw, uh = self.used_by.get_size()
        sw, sh = self.get_size()
        if cross:
            self.move(y = uy + int((uh - sh) / 2))
        else:
            self.move(x = ux + int((uw - sw) / 2))
        return self


    def to_left(self):
        '''
        Moves this label to the left edge of the widget that uses it

        Returns:
            Widget: Alias to this widget
        '''
        ux = self.used_by.get_position()[0]
        self.move(x = ux)
        return self


    def to_right(self):
        '''
        Moves this label to the right edge of the widget that uses it

        Returns:
            Widget: Alias to this widget
        '''
        ux = self.used_by.get_position()[0]
        uw = self.used_by.get_size()[0]
        sw = self.get_size()[0]
        self.move(x = ux + uw - sw)
        return self


    def to_top(self):
        '''
        Moves this label to the top edge of the widget that uses it

        Returns:
            Widget: Alias to this widget
        '''
        uy = self.used_by.get_position()[1]
        self.move(y = uy)
        return self


    def to_bottom(self):
        '''
        Moves this label to the bottom edge of the widget that uses it

        Returns:
            Widget: Alias to this widget
        '''
        uy = self.used_by.get_position()[1]
        uh = self.used_by.get_size()[1]
        self.move(y = uy + uh - 1)
        return self


class Labeled(ContentWidget):
    '''
    Class of widgets where each displays its label in a separate sibling
    widget, allowing label to be displayed outside of this widget's bounds

    Attributes:
        _linked_label (weakref<Widget>): Widget to use for this widget's label
    '''
    @property
    def linked_label(self):
        ''' Getter for "linked_label" property '''
        return self._linked_label() if self._linked_label else None


    def __init__(self, label, parent, focus_key = None):
        # Initialize inherited state.
        super().__init__(label, parent, focus_key)

        # Insert label node into the tree of widgets.
        label = Label(parent, used_by = self)

        # Link this widget to the label.
        ref = weakref.ref(label)
        self._linked_label = ref
        self._links.append(ref)


class FlipSwitch(Labeled):
    '''
    Boolean state widget

    Attributes:
        _init_state (bool): Switch state upon receiving focus
        _on (bool): Flag indicating if this widget is switched on
    '''
    def __init__(self, label, parent, focus_key = None):
        # Initialize inherited state.
        super().__init__(label, parent, focus_key)
        self._overrides_enter = True

        # Initialize attributes.
        self._init_state = False
        self._on = False

        # Initialize size.
        self.resize(10, 3)


    def report(self):
        return {'usage': 'Enter:Toggle'}


    def focus(self, **kwargs):
        # Store initial switch state.
        self._init_state = self._on


    def compose(self):
        return (self._on != self._init_state, {'enabled': self._on})


    def draw(self):
        width = self.get_size()[0]
        half_width = width // 2

        # Draw a border around the switch.
        self.draw_border()

        # Draw switch to the right-side if on; left-side otherwise.
        if self._on:
            self.draw_border(offset_left = half_width)
        else:
            self.draw_border(offset_right = half_width)

        # Indicate switch state.
        text = 'ON' if self._on else 'OFF'
        margin = (2, half_width, 1, 1) if self._on else (half_width, 1, 1, 1)
        self.draw_text(text, row = margin[2], margin = margin, attr = self.style('text') | curses.A_BOLD)


    def operate(self, c):
        # Toggle switch state.
        if c in {curses.KEY_ENTER, ascii.LF, ascii.CR}:
            self.tag_redraw()
            self._on = not self._on
        return 'CONTINUE'


class NavPage(ContentWidget):
    '''
    Container for widgets that is controlled by a navigation list
    '''
    def __init__(self, label, parent, focus_key = None):
        # Initialize inherited state.
        super().__init__(label, parent, focus_key)


    def draw(self):
        # Draw a border around the page.
        self.draw_border()

        # Indicate selection in navlist.
        left_arrow = u'\u25C0'
        self.draw_text(left_arrow, row = self._parent._selection + 1)


class NavList(Labeled):
    '''
    Navigable list of containers for widgets (pages)

    Attributes:
        _page_list (list<NavPage>): List of associated pages
        _highlight (int): Index in page list of highlighted option
        _selection (int): Index in page list of selected option
        _list_width (int): Width of this widget reserved for list
    '''
    @property
    def list_width(self):
        ''' Getter for "list_width" property '''
        return self._list_width


    @list_width.setter
    def list_width(self, value):
        ''' Setter for "list_width" property '''
        # Set value.
        self._list_width = value

        # Update position of navlist's label.
        linked_label = self.linked_label
        linked_label.to_top().to_left().embellish(' ', ' ')
        linked_label.offset(x = (value - len(linked_label._label)) // 2)


    def __init__(self, label, parent, focus_key = None):
        # Initialize inherited state.
        super().__init__(label, parent, focus_key)
        self._overrides_enter = True

        # Initialize attributes.
        self._page_list = []
        self._highlight = 0
        self._selection = None
        self.list_width = 15


    def focus(self, **kwargs):
        # Highlight selected page.
        self._highlight = self._selection if self._selection else 0


    def new_page(self, label):
        '''
        Creates a page and inserts it into this navlist

        Parameters:
            label (str): Identifier for page in navlist

        Returns:
            NavPage: Alias to created page
        '''
        # Create a widget to serve as a container for page elements.
        page = NavPage(label, self)

        # Select the first page by default.
        if self._page_list:
            page.hide()
        else:
            self._selection = 0

        # Associate page with this navlist.
        self._page_list.append(page)

        # Initialize page layout.
        sx, sy = self.get_position()
        sw, sh = self.get_size()
        list_width = self.list_width
        page.resize(sw - list_width, sh)
        page.move(sx + list_width - 2, sy)

        return page


    def draw(self):
        page_list = self._page_list
        selection = self._selection
        selected_page = page_list[selection] if selection >= 0 else None
        margin = (1, self.get_size()[0] - self.list_width + 1, 1, 1)
        padding = (1, 1)

        # Draw a border around the navlist.
        self.draw_border(offset_right = margin[1] - 1)

        # Draw navlist options.
        for i in range(len(page_list)):
            page = page_list[i]
            attr = self.style('highlight') if i == self._highlight else self.style('text')
            self.draw_text(page._label, row = i + margin[2], padding = padding, margin = margin, expand = 'RIGHT', attr = attr)


    def operate(self, c):
        page_list = self._page_list
        selection = self._selection
        selected_page = page_list[selection] if selection >= 0 else None

        if c in {curses.KEY_DOWN, curses.KEY_UP, curses.KEY_ENTER, ascii.LF, ascii.CR}:
            self.tag_redraw()

            # Highlight the next option, wrapping if necessary.
            if c == curses.KEY_DOWN:
                self._highlight += 1
                self._highlight %= len(page_list)

            # Highlight the previous option, wrapping if necessary.
            elif c == curses.KEY_UP:
                self._highlight -= 1
                self._highlight %= len(page_list)

            # Select the highlighted option.
            elif c in {curses.KEY_ENTER, ascii.LF, ascii.CR}:
                self._select(self._highlight)

        return 'CONTINUE'


    def _select(self, page_idx):
        '''
        Selects given page in the navlist and transfers input focus

        Parameters:
            page_idx: Index of page in navlist
        '''
        page_list = self._page_list
        selection = self._selection

        # Select indexed page.
        if page_idx >= 0 and page_idx < len(page_list):

            # Update visibility states.
            page_list[selection].hide()
            page_list[page_idx].show()

            # Set selection and transfer input focus.
            self._selection = page_idx
            Widget.input_focus = page_list[page_idx]


class TextBox(Labeled):
    '''
    Multi-line text input/display widget

    Parameters:
        _text (str): Text content
        _cursor_offset: Position of cursor relative to beginning of the text
        _col_scroll (int): Index corresponding to left of viewable region
        _row_scroll (int): Index corresponding to top of viewable region
        _read_only (bool): Flag controlling ability to edit this widget
    '''
    def __init__(self, label, parent, focus_key = None):
        # Initialize inherited state.
        super().__init__(label, parent, focus_key)
        self._overrides_enter = True

        # Initialize attributes.
        self._text = ''
        self._cursor_offset = 0
        self._col_scroll = 0
        self._row_scroll = 0
        self._read_only = False


    def clear(self, **kwargs):
        self._text = ''
        self._cursor_offset = 0
        self._col_scroll = 0
        self._row_scroll = 0


    def report(self):
        usage = 'Up/Down/Left/Right: Move Cursor'
        if not self._read_only:
            usage = 'Type text input. Up/Down/Left/Right: Move Cursor'
        else:
            usage = 'Up/Down/Left/Right: Scroll'
        return {'usage': usage}


    def compose(self):
        return (not self._read_only and self._text != '', {'text': self._text})


    def decompose(self, text, **kwargs):
        self.clear()
        self._text = text


    def draw(self):
        margin = [2, 3, 1, 1]
        width, height = self.get_size()
        effective_width = width - margin[0] - margin[1]
        effective_height = height - margin[2] - margin[3]
        text = self._text
        offset = self._cursor_offset
        col_scroll = self._col_scroll
        row_scroll = self._row_scroll

        # Draw border around the text box.
        self.draw_border(offset_right = 1)

        # Draw lines of text.
        line_list = self._build_line_list()
        for i in range(min(len(line_list[row_scroll:]), effective_height)):
            line = line_list[i + row_scroll]
            self.draw_text(line[col_scroll:], row = i + margin[2], margin = margin, fit = 'NO_WRAP')

        # Draw the cursor.
        if not self._read_only:
            col_offset, row_offset = self._split_offset(offset)
            self.draw_cursor(col_offset + margin[0] - col_scroll, row_offset + margin[2] - row_scroll, margin = margin)

        # Indicate if content exists outside of the visible region.
        attr = self.style('border')
        padding = (1, 1)
        center_row = math.ceil(height / 2) - 1

        # Indicate content before.
        if col_scroll > 0:
            left_arrow = u'\u25C0'
            self.draw_text(left_arrow, row = center_row, align = 'LEFT', attr = attr)

        # Indicate content after.
        num_cols = max([len(i) for i in text.splitlines() or [text]])
        if col_scroll < num_cols - effective_width:
            right_arrow = u'\u25B6'
            self.draw_text(right_arrow, row = center_row, margin = (width - 2, 0, 0, 0), attr = attr)

        # Indicate content above.
        if row_scroll > 0:
            up_arrow = u'\u25B2'
            self.draw_text(up_arrow, padding = padding, align = 'CENTER', attr = attr)

        # Indicate content below.
        num_rows = len(line_list)
        if row_scroll < num_rows - effective_height:
            down_arrow = u'\u25BC'
            self.draw_text(down_arrow, row = height - 1, padding = padding, align = 'CENTER', attr = attr)


    def operate(self, c):
        margin = [2, 3, 1, 1]
        width, height = self.get_size()
        effective_width = width - margin[0] - margin[1]
        effective_height = height - margin[2] - margin[3]
        text = self._text
        offset = self._cursor_offset
        col_offset, row_offset = self._split_offset(self._cursor_offset)
        col_scroll = self._col_scroll
        row_scroll = self._row_scroll

        # Enforce read-only constraint.
        if not self._read_only:

            # Add a character.
            if (ascii.isprint(c)
                or c in {curses.KEY_ENTER, ascii.LF, ascii.CR}
            ):
                self.tag_redraw()

                # Insert character before the cursor.
                self._text = text[:offset] + chr(c) + text[offset:]

                # Update offset of the cursor.
                self._cursor_offset += 1

            # Delete a character.
            elif (c in {ascii.BS, ascii.DEL, curses.KEY_BACKSPACE}
                  and offset > 0
            ):
                self.tag_redraw()

                # Delete character preceding the cursor.
                self._text = text[:offset - 1] + text[offset:]

                # Update offset of the cursor.
                self._cursor_offset -= 1

            # Move cursor left unless start of either text or line is
            # encountered.
            if (c == curses.KEY_LEFT
                and offset > 0
                and ord(text[offset - 1]) not in {
                    curses.KEY_ENTER, ascii.LF, ascii.CR
                }
            ):
                self.tag_redraw()
                self._cursor_offset -= 1

            # Move cursor right unless end of either text or line is
            # encountered.
            elif (c == curses.KEY_RIGHT
                  and offset < len(text)
                  and ord(text[offset]) not in {
                      curses.KEY_ENTER, ascii.LF, ascii.CR
                }
            ):
                self.tag_redraw()
                self._cursor_offset += 1

            # Move cursor up.
            elif c == curses.KEY_UP:
                self.tag_redraw()
                self._cursor_offset = self._join_offsets(col_offset, row_offset - 1)

            # Move cursor down.
            elif c == curses.KEY_DOWN:
                self.tag_redraw()
                self._cursor_offset = self._join_offsets(col_offset, row_offset + 1)


            # Scroll if necessary.
            col_offset, row_offset = self._split_offset(self._cursor_offset)
            if col_offset < col_scroll:
                self._col_scroll = col_offset
            elif col_offset > col_scroll + effective_width - 1:
                self._col_scroll += col_offset - (col_scroll + effective_width - 1)
                self._col_scroll = col_offset - (effective_width - 1)
            if row_offset < row_scroll:
                self._row_scroll = row_offset
            elif row_offset > row_scroll + effective_height - 1:
                self._row_scroll = row_offset - (effective_height - 1)

        else: # Read-only mode
            line_list = self._build_line_list()
            num_cols = max([len(i) for i in line_list])
            num_rows = len(line_list)
            scroll_sensitivity = 1

            # Scroll left.
            if c == curses.KEY_LEFT:
                self.tag_redraw()
                self._col_scroll = max(0, col_scroll - 2 * scroll_sensitivity)

            # Scroll right.
            elif c == curses.KEY_RIGHT:
                self.tag_redraw()
                self._col_scroll = min(
                    col_scroll + 2 * scroll_sensitivity,
                    max(0, num_cols - effective_width)
                )

            # Scroll up.
            elif c == curses.KEY_UP:
                self.tag_redraw()
                self._row_scroll = max(0, row_scroll - 1 * scroll_sensitivity)

            # Scroll down.
            elif c == curses.KEY_DOWN:
                self.tag_redraw()
                self._row_scroll = min(
                    row_scroll + 1 * scroll_sensitivity,
                    max(0, num_rows - effective_height)
                )

        return 'CONTINUE'


    def read_only(self):
        ''' Prevents editing of this widget '''
        self._read_only = True

        # Remove default navigation overrides.
        self._overrides_enter = False


    def _build_line_list(self, strip = False):
        '''
        Builds lines of text from the string of text content

        Parameters:
            strip (bool): Flag controlling removal of trailing, blank lines

        Returns:
            list<str>: Lines of text
        '''
        # Build line list from text content.
        line_list = self._text.splitlines() or [self._text]

        # Remove any trailing blank lines.
        if strip:
            while len(line_list) > 1 and line_list[-1].strip() == '':
                line_list.pop()

        return line_list


    def _join_offsets(self, col_offset, row_offset):
        '''
        Calculates linear offset with line-breaks from 2-dimensional offset

        Parameters:
            col_offset (int): Horizontal offset value
            row_offset (int): Vertical offset value

        Returns:
            int: Linear offset value
        '''
        offset = 0
        line_list = self._build_line_list()
        row_offset = max(0, min(row_offset, len(line_list) - 1))
        for line in line_list[:row_offset]:
            offset += len(line) + 1
        offset += min(col_offset, len(line_list[row_offset]))
        return offset


    def _split_offset(self, offset):
        '''
        Calculates 2-dimensional offsets from linear offset and line-breaks

        Parameters:
            offset (int): Linear offset value

        Returns:
            2-tuple: horizontal offset (int), vertical offset (int)
        '''
        col = max(0, offset)
        row = 0
        line_list = self._build_line_list()
        for line in line_list:
            line_len = len(line) if line else 0
            if line_len >= col:
                break;
            row += 1
            col -= line_len + 1
        return col, row


class NumericField(Labeled):
    '''
    Integer input widget

    Attributes:
        _number (str): String representation of number
    '''
    def __init__(self, label, parent, focus_key = None):
        # Initialize inherited state.
        super().__init__(label, parent, focus_key)

        # Initialize attributes.
        self._number = ''

        # Initialize height.
        self.resize(height = 3)


    def clear(self, **kwargs):
        self._number = ''

    def report(self):
        return {'usage': 'Enter numeric input.'}


    def compose(self, **kwargs):
        return (
            self._number != '',
            {'number': int(self._number) if self._number else None}
        )


    def draw(self):
        margin = [2, 2, 1, 1]
        number = self._number

        # Draw border around the text field.
        self.draw_border()

        # Draw the numeric input.
        self.draw_text(number, row = 1, padding = (0, 1), margin = margin, fit = 'CLIP_LEFT')

        # Draw the cursor.
        margin[0] = min(len(number) + margin[0], self.get_size()[0] - margin[1] - 1)
        self.draw_cursor(margin[0], 1, margin = margin)


    def operate(self, c):
        # Add a digit.
        if ascii.isdigit(c):
            self.tag_redraw()
            self._number += chr(c)

        # Delete a character.
        elif c in {ascii.BS, ascii.DEL, curses.KEY_BACKSPACE}:
            self.tag_redraw()
            self._number = self._number[:-1]

        return 'CONTINUE'


class TextField(Labeled):
    '''
    Text input widget

    Attributes:
        _text (str): Text input
        _is_obscured (bool): Flag controlling whether or not text is obscured
    '''
    def __init__(self, label, parent, focus_key = None):
        # Initialize inherited state.
        super().__init__(label, parent, focus_key)

        # Initialize attributes.
        self._text = ''
        self._is_obscured = False

        # Initialize height.
        self.resize(height = 3)


    def clear(self, **kwargs):
        self._text = ''


    def report(self):
        return {'usage': 'Type text input.'}


    def compose(self, **kwargs):
        return (True, {'text': self._text})


    def draw(self):
        margin = [2, 2, 1, 1]

        # Draw border around the text field.
        self.draw_border()

        # Draw the text input.
        text = self._text
        text = '*' *  len(text) if self._is_obscured else text
        self.draw_text(text, row = 1, padding = (0, 1), margin = margin, fit = 'CLIP_LEFT')

        # Draw the cursor.
        margin[0] = min(len(text) + margin[0], self.get_size()[0] - margin[1] - 1)
        self.draw_cursor(margin[0], 1, margin = margin)


    def operate(self, c):
        # Add a character.
        if ascii.isprint(c):
            self.tag_redraw()
            self._text += chr(c)

        # Delete a character.
        elif c in {ascii.BS, ascii.DEL, curses.KEY_BACKSPACE}:
            self.tag_redraw()
            self._text = self._text[:-1]

        return 'CONTINUE'


    def obscure(self):
        ''' Obscures text input behind asterisks '''
        self._is_obscured = True;


    def reveal(self):
        ''' Reveals text input '''
        self._is_obscured = False;


class SelectField(Labeled):
    '''
    Enumerated input widget

    Attributes:
        _options (list<str>): Enumerated input options
        _options_limit (int): Maximum number of options to display
        _highlight (int): Highlighted index in list of options
        _init_highlight (int): Highlight index at the time of gaining focus
        _row_scroll (int): Index corresponding to top of viewable region
        _expanded (bool): Flag indicating if options list is expanded/collapsed
        _overlayed (bool): Flag indicating if expanded options list has been
            drawn over siblings
        _auto_expand (bool): Flag controlling automated expansion of options
    '''
    def __init__(self, label, parent, focus_key = None):
        # Initialize inherited state.
        super().__init__(label, parent, focus_key)

        # Initialize attributes.
        self._options = ['-- NO SELECTION --']
        self._options_limit = -1
        self._highlight = 0
        self._init_highlight = 0
        self._row_scroll = 0
        self._auto_expand = False
        self.collapse()


    def clear(self, **kwargs):
        self._options = ['-- NO SELECTION --']
        self._highlight = 0


    def report(self):
        return {'usage': 'Up/Down:Scroll, Enter:Select'}


    def compose(self):
        highlight = self._highlight
        option = self._options[highlight]
        selection_changed = highlight != self._init_highlight
        return (selection_changed, {'option': option if highlight > 0 else None})


    def decompose(self, options, **kwargs):
        # Load options and update draw state.
        self.load_options(options)
        if self._expanded:
            self.expand()


    def focus(self, **kwargs):
        # Store initial highlighted option.
        self._init_highlight = self._highlight

        # Expand options list on focus.
        if self._auto_expand:
            self.expand()


    def blur(self):
        # Collapse options list on blur if automated.
        if self._auto_expand:
            self.collapse()


    def draw(self):
        width, height = self.get_size()
        margin = [1, 1, 1, 1]
        padding = (1, 1)

        # Draw border around the text field.
        self.draw_border()

        # Draw the list of options.
        row_scroll = self._row_scroll
        options_section = self._options[row_scroll:][:height - 2]
        for i in range(len(options_section)):
            option = options_section[i]

            # Format and style option.
            expand = 'AROUND' if not i + row_scroll else 'RIGHT'
            if i + row_scroll == self._highlight:
                attr = self.style('highlight')
            else:
                attr = self.style('text')

            # Draw option.
            self.draw_text(option, row = margin[2] + i, margin = margin, padding = padding, expand = expand, attr = attr)

        # Indicate if content exists outside of the visible region.
        if Widget.input_focus is self:
            attr = self.style('border')
            padding = (1, 1)

            # Indicate content above.
            up_arrow = u'\u25B2'
            if self._row_scroll > 0:
                self.draw_text(up_arrow, padding = padding, align = 'CENTER', attr = attr)

            # Indicate content below.
            down_arrow = u'\u25BC'
            if self._row_scroll + height - 2 < len(self._options):
                self.draw_text(down_arrow, row = height - 1, padding = padding, align = 'CENTER', attr = attr)


    def operate(self, c):
        margin = [1, 1, 1, 1]

        # Draw expanded options list over siblings.
        if self._expanded and not self._overlayed:
            self.tag_redraw()
            self._overlayed = True

        if c in {curses.KEY_DOWN, curses.KEY_UP, curses.KEY_ENTER, ascii.LF, ascii.CR}:
            self.tag_redraw()

            # Highlight the next option, wrapping if necessary.
            if c == curses.KEY_DOWN:
                self._highlight += 1
                self._highlight %= len(self._options)

            # Highlight the previous option, wrapping if necessary.
            elif c == curses.KEY_UP:
                self._highlight -= 1
                self._highlight %= len(self._options)

            # Select the highlighted option.
            elif c in {curses.KEY_ENTER, ascii.LF, ascii.CR}:
                return 'END'

            # Scroll list if necessary.
            effective_height = self.get_size()[1] - margin[2] - margin[3]
            if self._highlight < self._row_scroll:
                self._row_scroll = self._highlight
            elif self._highlight >= self._row_scroll + effective_height:
                self._row_scroll = self._highlight - effective_height + 1

        return 'CONTINUE'


    def auto_expand(self):
        ''' Flags this widget for automated expansions of options list '''
        self._auto_expand = True


    def collapse(self):
        ''' Collapses the options list to display only a single option '''
        # Collapse options list.
        self.resize(height = 3)

        # Redraw siblings that may have been occluded by drop-down list.
        self._ancestor.tag_redraw()

        # Scroll to the highlighted option.
        self._row_scroll = self._highlight

        # Set state.
        self._expanded = False
        self._overlayed = False


    def expand(self):
        ''' Expands the options list to display multiple options '''
        # Expand options list.
        ph = self._parent.get_size()[1]
        sy = self.get_position()[1]
        option_count = ph if self._options_limit < 0 else self._options_limit
        option_count = min(option_count, ph - sy - 3)
        option_count = min(option_count, len(self._options))
        sh = option_count + 2
        self.resize(height = sh)

        # Set state.
        self._expanded = True


    def limit_options(self, count):
        '''
        Limits the number of options presented

        Parameters:
            count (int): Maximum number of options to display
        '''
        self._options_limit = max(1, count)
        if self._expanded:
            self.expand()


    def load_options(self, options):
        '''
        Loads enumerated options from a list

        Parameters:
            options (list<str>): Options list
        '''
        self._options = ['-- NO SELECTION --']
        self._options.extend(options)
        if self._expanded:
            self.expand()


class Table(Labeled):
    '''
    Display widget for tabulated data

    Parameters:
        _header (list<str>): Column names for tabulated data
        _body (list<str>): Rows of tabulated data
        _col_widths (list<int>): Span of each column in characters
        _col_scroll (int): Index corresponding to left of viewable region
        _row_scroll (int): Index corresponding to top of viewable region
    '''
    def __init__(self, label, parent, focus_key = None):
        # Initialize inherited state.
        super().__init__(label, parent, focus_key)

        # Initialize attributes.
        self.clear()


    def clear(self, **kwargs):
        self._header = []
        self._body = []
        self._col_widths = []
        self._col_scroll = 0
        self._row_scroll = 0


    def report(self):
        return {'usage': 'Up/Down/Left/Right/PgUp/PgDn: Scroll'}


    def decompose(self, table = [], pretty_print = '', **kwargs):
        self.tag_redraw()
        self.clear()

        # Parse ASCII "Pretty Print" text, if available.
        if pretty_print:
            table = [
                [item.strip() for item in row.split('|')[1:-1]]
                for row in pretty_print.splitlines()
                if row[0] == '|'
            ]

        # Convert table items into strings.
        table = [[str(item) if type(item) in {int, str} else '' for item in row] for row in table]

        # Separate table data into header and body sections.
        self._header = table[0]
        self._body = table[1:]

        # Calculate the maximum width of each column.
        self._col_widths = [
            max([len(row[i]) + 4 for row in table])
            for i in range(len(self._header))
        ]
        self._col_widths[-1] -= 4

        # Validate received data.
        header_len = len(self._header)
        for row in self._body:

            # Clear table data, and indicate error.
            if len(row) != header_len:
                self.clear()
                signal = signals.Signal(
                    'UI_FEEDBACK',
                    message = 'Mismatch between table header & body column counts',
                    error = True
                )
                self.bubble(**signal.data)
                break;


    def draw(self):
        width, height = self.get_size()
        margin = [2, 3, 1, 1]
        effective_width = width - margin[0] - margin[1]
        effective_height = height - margin[2] - margin[3] - 2
        header = self._header
        body = self._body
        col_widths = self._col_widths
        col_scroll = self._col_scroll
        row_scroll = self._row_scroll

        # Draw border around both the table and header section.
        self.draw_border(offset_right = 1)
        self.draw_border(
            offset_bottom = height - 3, offset_right = 1,
            char_bottom_left = curses.ACS_LTEE, char_bottom_right = curses.ACS_RTEE
        )

        # Draw the table header.
        line = ''.join([
            '{:<{}}'.format(header[i], col_widths[i])
            for i in range(len(header))
        ])
        self.draw_text(line[col_scroll:], row = margin[2], margin = margin, fit = 'NO_WRAP')
        margin[2] += 2

        # Draw the table body.
        for i in range(min(len(body[row_scroll:]), effective_height)):
            line = ''.join([
                '{:<{}}'.format(body[i + row_scroll][j], col_widths[j])
                for j in range(len(body[i + row_scroll]))
            ])
            self.draw_text(line[col_scroll:], row = margin[2], margin = margin, fit = 'NO_WRAP')
            margin[2] += 1

        # Indicate if content exists outside of the visible region.
        attr = self.style('border')
        padding = (1, 1)
        center_row = math.ceil(height / 2) - 1

        # Indicate content before.
        if col_scroll > 0:
            left_arrow = u'\u25C0'
            self.draw_text(left_arrow, row = center_row, align = 'LEFT', attr = attr)

        # Indicate content after.
        if col_scroll < sum(col_widths) - effective_width:
            right_arrow = u'\u25B6'
            self.draw_text(right_arrow, row = center_row, margin = (width - 2, 0, 0, 0), attr = attr)

        # Indicate content above.
        if row_scroll > 0:
            up_arrow = u'\u25B2'
            self.draw_text(up_arrow, padding = padding, align = 'CENTER', attr = attr)

        # Indicate content below.
        if row_scroll < len(body) - effective_height:
            down_arrow = u'\u25BC'
            self.draw_text(down_arrow, row = height - 1, padding = padding, align = 'CENTER', attr = attr)


    def operate(self, c):
        margin = [2, 3, 3, 1]
        width, height = self.get_size()
        effective_width = width - margin[0] - margin[1]
        effective_height = height - margin[2] - margin[3]
        body = self._body
        col_widths = self._col_widths
        col_scroll = self._col_scroll
        row_scroll = self._row_scroll
        scroll_sensitivity = 1

        # Scroll left.
        if c == curses.KEY_LEFT:
            self.tag_redraw()
            self._col_scroll = max(0, col_scroll - 2 * scroll_sensitivity)

        # Scroll right.
        elif c == curses.KEY_RIGHT:
            self.tag_redraw()
            self._col_scroll = min(
                col_scroll + 2 * scroll_sensitivity,
                max(0, sum(col_widths) - effective_width)
            )

        # Scroll up.
        elif c == curses.KEY_UP:
            self.tag_redraw()
            self._row_scroll = max(0, row_scroll - 1 * scroll_sensitivity)

        # Scroll down.
        elif c == curses.KEY_DOWN:
            self.tag_redraw()
            self._row_scroll = min(
                row_scroll + 1 * scroll_sensitivity,
                max(0, len(self._body) - effective_height)
            )

        # Scroll up a full page.
        elif c == curses.KEY_PPAGE:
            self.tag_redraw()
            self._row_scroll = max(0, row_scroll - effective_height * scroll_sensitivity)

        # Scroll down a full page.
        elif c == curses.KEY_NPAGE:
            self.tag_redraw()
            self._row_scroll = min(
                row_scroll + effective_height * scroll_sensitivity,
                max(0, len(self._body) - effective_height)
            )

        return 'CONTINUE'
