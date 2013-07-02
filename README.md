Xinput-UI
=========

Xinput-UI is a GUI front-end to the xinput utility, allowing graphical control
over X.Org's Multi-Pointer X (MPX) features. It was created mainly as a
project to learn wxPython. The code is pretty horrible and has been cobbled 
together from several tutorials.

Using
-----

MPX, which has been in X.Org for a while now, allows the creation of multiple
"virtual" pointers. These virtual pointers are also called "master pointers."
Each master pointer can have any number of physical input devices (mice and
keyboards) slaved to it. A physical input device which isn't slaved to any 
master pointer is called a "floating slave." This is can all be configured in
xorg.conf, or with the "xinput" command-line utility as described here:
    https://wiki.archlinux.org/index.php/Multi-pointer_X

Xinput-UI provides a GUI interface to basic functionality of xinput. It
displays information about the virtual and physical input devices available on
the system. It allows the creation and deletion of master pointers, and the
reassignment of physical mice and keyboards between different master pointers.
However, it does not expose the more more advanced functionality of xinput,
such as setting or viewing device properties.

The main interface consists of a tree view of all virtual and physical input
devices. Physical input devices can be dragged between different master
pointers, or dragged over to the special "Unattached Devices" group to "float"
them.

Additional actions can be performed by right-clicking on physical or master
devices. For example, you can delete a master device by right-clicking on it
and selecting "delete." Some actions can also be undone through the right-
click menu. For example, to move a physical device back to its original master
pointer, right-click on it and select "cancel reattach."

At the bottom of the window, there is a list of pending commands. These are 
the xinput commands that have been generated to perform the actions you have
selected. None of them will actually be run until you click "apply." 

There is a button to add a new master pointer. New master pointers cannot have
any physical devices added to them until you click "apply." 

The "refresh" button will discard all pending changes and reload the list of 
devices. If you plug in a new input device, you'll have to hit "refresh" or it
won't show up.

If a master pointer is selected, the "remove" button will detach all physical 
devices from it and mark it for deletion. If a physical device is selected,
the "remove" button will detach it.

Notes
-----

Xinput-UI parses the text output of the xinput utility directly. As such, it
may be sensitive to changes in xinput's text formatting. 

The xinput utility does not allow any way to determine whether a floating
slave is a keyboard or a mouse. Because of this, I've elected not to
distinguish between them at all, even for attached slave devices. The user
interface does not indicate whether a device is a mouse or a keyboard. When 
attaching a physical input device to a master pointer, Xinput-UI does so by
brute force, first trying to attach it as a mouse, then as a keyboard. This is
why two commands are created for each attach operation, and why you'll see
lots of error messages on stderr if you run this program from a command line:
one of those two commands is guaranteed to fail. The "Right Way" to solve this
would involve creating a C module, using source code adapted directly from the
xinput utility itself. If I ever decide to learn the Python-C API, I may do 
that.

Xinput-UI doesn't yet provide any way to save the MPX configuration, so it 
will be lost when the X session ends. A way to save the configuration to a 
file in xorg.conf.d, or a way to save and load presets, might be a good idea.

License
-------

Xinput-UI is released under the MIT License. There's a copy of it included 
with the program.
