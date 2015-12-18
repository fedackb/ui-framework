# Filename: signals.py
# Creation Date: Thu 08 Oct 2015
# Last Modified: Wed 18 Nov 2015 07:39:00 PM MST
# Author: Brett Fedack


import inspect
import weakref


class Signal():
    '''
    Data carrying signal class

    Attributes:
        _name (str): Signal identifier
        _data (dict): Data carried by a signal; expanded to handler arguments
        _propagate (bool): Flag controlling whether or not a signal can be
            handled multiple times
    '''
    def __init__(self, name, data = dict(), propagate = True, **kwargs):
        '''
        Parameters:
            name (str): _name attribute initializer
            data (dict): _data attribute initializer (Optional)
            propagate (bool): _propagate attribute initializer (Optional)
        '''
        self._name = name
        self._data = data if data else {}
        self._propagate = propagate

        # Include all other keyword arguments in carried data.
        self._data.update(kwargs)

        # Include signal name and propagation flag in carried data.
        self._data['_name'] = name
        self._data['_propagate'] = propagate


    @property
    def data(self):
        '''Getter for "data" property '''
        return self._data


class SignalRouter():
    '''
    Mediator for managing signal handlers and forwarding received signals

    Attributes:
        _signal_handlers (dict): Signal handler lists keyed by signal name
    '''
    def __init__(self):
        self._signal_handlers = dict()


    def forward(self, signal, reverse = False):
        '''
        Forwards the given signal to registered signal handlers

        Parameters:
            signal (Signal): Received signal to forward
            reverse (bool): Flag controlling order of signal handler traversal
                (Optional)

        Returns:
            bool: True if given signal is forwarded; False otherwise
        '''
        signame = signal.data['_name']
        propagate = signal.data['_propagate']

        # Determine if the signal can be handled.
        if signame in self._signal_handlers:

            # Create a shallow working copy of the signal handlers list.
            handlers_list = self._signal_handlers[signame].copy()
            if reverse:
                handlers_list.reverse()

            # Visit registered signal handlers in order.
            for handler in handlers_list:

                # Handle the signal.
                handler()(**signal.data) # Called from weak reference

                # Only handle once if the signal cannot propagate.
                if not propagate:
                    break

            return True
        return False


    def register(self, signame, handler):
        '''
        Registers the given signal handler for signal forwarding

        Parameters:
            signame (str): Signal name
            handler (method|function): Signal handler

        Returns:
            (bool): True if handler is registered; False otherwise '''
        # Create a weak reference to the function/method handler.
        if inspect.ismethod(handler):
            handler = weakref.WeakMethod(handler)
        elif inspect.isfunction(handler):
            handler = weakref.ref(handler)
        else:
            return False

        # Add given non-duplicate handler to respective signal handlers list.
        if signame in self._signal_handlers:
            if handler not in self._signal_handlers[signame]:
                self._signal_handlers[signame].append(handler)
                return True
        else:
            self._signal_handlers[signame] = [handler]
            return True
        return False

    def deregister(self, signame, handler):
        '''
        Deregisters given signal handler

        Parameters:
            signame (str): Signal name
            handler (method|function): Signal handler

        Returns:
            (bool): True if handler is deregistered; False otherwise
        '''
        # Compare function/method handlers by weak reference.
        if inspect.ismethod(handler):
            handler = weakref.WeakMethod(handler)
        elif inspect.isfunction(handler):
            handler = weakref.ref(handler)
        else:
            return False

        # Remove given handler from respective signal handlers list.
        if (signame in self._signal_handlers
            and handler in self._signal_handlers[signame]
        ):
            self._signal_handlers[signame].remove(handler)

            # Remove signal name if it is associated with an empty list.
            if not self._signal_handlers[signame]:
                del self._signal_handlers[signame]

            return True
        return False
