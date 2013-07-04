#! /usr/bin/env python2.7

# xinput-ui
# A GUI front-end for the xinput utility, allowing graphical control over 
# X.Org's Multi-Pointer X (MPX) features. Created mainly as a project to learn 
# wxPython. The code is pretty horrible and has been cobbled together from 
# several tutorials.

# Copyright (c) 2013 Max Eliaser
#
# Permission is hereby granted, free of charge, to any person obtaining a
# copy of this software and/or associated documentation files (the
# "Materials"), to deal in the Materials without restriction, including
# without limitation the rights to use, copy, modify, merge, publish,
# distribute, sublicense, and/or sell copies of the Materials, and to
# permit persons to whom the Materials are furnished to do so, subject to
# the following conditions:
#
# The above copyright notice and this permission notice shall be included
# in all copies or substantial portions of the Materials.
#
# THE MATERIALS ARE PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
# IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY
# CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT,
# TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE
# MATERIALS OR THE USE OR OTHER DEALINGS IN THE MATERIALS.

# Sources I used:
#  - http://zetcode.com/wxpython/
#  - http://wiki.wxpython.org/

import wx, wx.gizmos
import subprocess
from string import whitespace as str_whitespace
import operator

INVALID_ID = -2
FLOATING_ID = -1

def run_command (command):
    p = subprocess.Popen(command,
                         stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT)
    return iter(p.stdout.readline, b'')

def mystrip (string):
    """Strip the extra Unicode characters "xinput list" likes to output."""
    str_special = '\xe2\x8e\xa1\xe2\x8e\x9c\xe2\x86\xb3\xe2\x8e\xa3\x88\xbc'
    return string.strip(str_whitespace+str_special)

def device_sort (device_set):
    """Sort a set of devices by self_id. Can't be used with PendingDevices!"""
    return sorted(device_set, key = operator.attrgetter ('self_id'))

# These device classes must all have a public "name" attribute

class MasterDevice:
    
    """A master pointer/keyboard pair that exists in the X server.
    
    Attributes:
    name        --  A string used for display purposes.
    pointer_id  --  The numeric ID of the master pointer of the pair.
                    This is either a value assigned by the X server, or the
                    special value FLOATING_ID.
    keyboard_id --  The numeric ID of the master keyboard of the pair.
                    This is either a value assigned by X server, or the
                    special value FLOATING_ID.
    self_id     --  Always the same as pointer_id. This is what is used to 
                    uniquely identify the device.
    children    --  A set of SlaveDevice objects corresponding to the physical
                    input hardware devices that are CURRENTLY slaved to the
                    pair. 
    
    FLOATING_ID is used on only one instance of MasterDevice. This special
    instance doesn't correspond to a pointer/keyboard pair that actually
    exits, but is rather used to group all the "floating" (un-slaved) hardware
    input devices together.
    
    """
    
    def __init__ (self, name):
        self.name = name
        self.children = set()
        self.self_id = self.pointer_id = self.keyboard_id = INVALID_ID
        self.expanded = True
    
    def set_pointer_id (self, pointer_id):
        """MUST be called before any devices are slaved!"""
        self.pointer_id = pointer_id
        self.self_id = pointer_id # for device_sort
    
    def set_keyboard_id (self, keyboard_id):
        """MUST be called before any devices are slaved!"""
        self.keyboard_id = keyboard_id
    
    def add_slave (self, slave_id, slave_name):
        """Creates a SlaveDevice."""
        assert self.self_id != INVALID_ID
        assert self.pointer_id != INVALID_ID
        assert self.keyboard_id != INVALID_ID
        self.children.add (SlaveDevice (self, slave_id, slave_name))

class SlaveDevice: # real physical hardware device
    
    """A slave (physical hardware) input device connected to the computer.
    
    Attributes:
    name    --  A string used for display purposes.
    self_id --  A numeric ID assigned by the X server.
    parent  --  The MasterDevice object that this device is CURRENTLY slaved 
                to in the X server. 
    
    """
    
    def __init__ (self, parent, self_id, name):
        self.self_id = self_id
        self.name = name
        self.parent = parent
    
class PendingDevice: # virtual device which is pending creation
    
    """A master pointer/keyboard pair which is pending creation.
    
    The user has given it a name, but it hasn't been actually created, so it
    doesn't have any numeric IDs assigned yet. Until pending changes are 
    applied, hardware input devices cannot be slaved to it.
    
    """
    
    def __init__ (self, name):
        self.name = name
        self.expanded = False #really doesn't matter which

def read_raw_device_data ():
    
    """Invokes the external program "xinput" and returns a "raw" device list.
    
    The output is cleaned up an split into lines and tokens, but still not
    very useful without further processing.
    
    """
    
    ret = {}
    
    for line in run_command (["/usr/bin/env", "xinput", "list"]):
        
        raw_device = [mystrip(field) for field in line.split ('\t')]
        raw_class_data = [field.strip('()') for field in raw_device[2][1:-1].split()]
        
        device_self_id = int (raw_device[1].split('=')[1])
        device_name = raw_device[0]
        
        # filter out XTEST devices
        if device_name.find ("XTEST") == -1:
            ret.update ({device_self_id: [device_name, raw_class_data]})
    
    return ret

def get_device_status ():
    
    """Returns a list of MasterDevice objects.
    
    Each of MasterDevice corresponds to a master pointer/master keyboard pair
    that currently exists in the X server. Each MasterDevice may also be
    populated with SlaveDevice objects.
    
    """
    
    unsorted_devices = read_raw_device_data ()
    
    all_masters = {}
    # same as all_masters but with duplicate entries for keyboard device IDs.
    all_master_aliases = {} 
    
    # initialize master devices
    
    device = MasterDevice ("Unattached Devices")
    device.set_pointer_id (FLOATING_ID)
    device.set_keyboard_id (FLOATING_ID)
    all_master_aliases.update ({FLOATING_ID: device})
    all_masters.update ({FLOATING_ID: device})

    for device_id, rawdevice in unsorted_devices.iteritems():
        if rawdevice[1][0] != 'master' or rawdevice[1][1] != 'pointer':
            continue
        device = MasterDevice (rawdevice[0])
        device.set_pointer_id (device_id)
        all_master_aliases.update ({device_id: device})
        all_masters.update ({device_id: device})
    
    for device_id, rawdevice in unsorted_devices.iteritems ():
        if rawdevice[1][0] != 'master' or rawdevice[1][1] != 'keyboard':
            continue
        device = all_master_aliases[int(rawdevice[1][2])]
        device.set_keyboard_id (device_id)
        all_master_aliases.update ({device_id: device})
    
    # initialize slave devices and attach them to their parent master devices
    
    for device_id, rawdevice in unsorted_devices.iteritems ():
        if rawdevice[1][0] == 'master':
            continue 
        master_id = None
        if rawdevice[1][0] == 'floating':
            master_id = FLOATING_ID
        else:
            master_id = int(rawdevice[1][2])
        all_master_aliases[master_id].add_slave (device_id, rawdevice[0])
    
    return all_masters

class DeviceTree (wx.gizmos.TreeListCtrl):
    
    """Tree list control widget displaying the master/slave device heirarchy.
    
    Inherits from wxPython's TreeListCtrl, and adds semantics to interactions
    like drag-and-drop, right-click, etc. This widget is completely emptied
    and regenerated every time something changes, because that's easier than
    constantly updating it to track current state.
    
    """
    
    def __init__ (self, UI, panel):
        
        self.UI = UI
        
        label = wx.StaticBox (panel, label = "Devices:")
        sizer = wx.StaticBoxSizer (label, wx.VERTICAL)
        
        super (DeviceTree, self).__init__(panel, style = wx.TR_HIDE_ROOT | wx.TR_DEFAULT_STYLE | wx.SUNKEN_BORDER)
        
        self.AddColumn ("Name", 350)
        self.AddColumn ("ID", 30)
        self.root = self.AddRoot ("Pointers")
        sizer.Add(self, flag = wx.EXPAND, proportion = 1)
        
        panel.SetMinSize ((-1, 75))
        
        panel.SetSizer (sizer)
        
        self.Bind (wx.EVT_TREE_BEGIN_DRAG, self.OnBeginDrag)
        self.Bind (wx.EVT_TREE_END_DRAG, self.OnEndDrag)
        self.Bind (wx.EVT_TREE_ITEM_RIGHT_CLICK, self.OnRightClick)
        
        self.Bind (wx.EVT_TREE_SEL_CHANGED, self.OnSelectItem)
        self.Bind (wx.EVT_TREE_ITEM_COLLAPSED, self.OnCollapseOrExpandItem)
        self.Bind (wx.EVT_TREE_ITEM_EXPANDED, self.OnCollapseOrExpandItem)
        
        self.delete_callback = None
        self.selection_context = None
    
    def UpdateDeviceName (self, device, menuitem):
        
        """Set the device's display name.
        
        Call this if the device's status changes and the display needs to 
        reflect the change.
        
        """
        
        # "Name" column
        self.SetItemText (menuitem, device.name + self.UI.changes.GetDeviceStatusText (device))
        
        if device.__class__ == SlaveDevice: # "ID" column
            self.SetItemText (menuitem, str(device.self_id), 1)
    
    def addMaster (self, device, slavelist):
        
        """Add widgets to display a MasterDevice and all its current slaves.
        
        Note that the widgets for the slaves may be moved to other groups by
        other methods to reflect pending changes.
        
        Called a bunch of times during initialization and refresh.
        
        """
        
        device_menuitem = self.AppendItem (self.root, "")
        self.SetItemPyData (device_menuitem, device)
        self.UpdateDeviceName (device, device_menuitem)
        
        for slave in device_sort(slavelist):
            slave_menuitem = self.AppendItem (device_menuitem, "")
            self.SetItemPyData (slave_menuitem, slave)
            self.UpdateDeviceName (slave, slave_menuitem)
        
        if device.expanded:
            self.Expand (device_menuitem)
    
    def DeleteAllItems (self, *args, **kwargs):
        
        """Wrapped wxWidgets method."""
        
        super (DeviceTree, self).DeleteAllItems (*args, **kwargs)
        
        self.root = self.AddRoot ("Pointers")
    
    def OnBeginDrag (self, evt):
        
        """Drag-and-drop callback: start dragging."""
        
        it = self.GetItemPyData (evt.GetItem ())
        self.dragItem = None
        if it.__class__ != SlaveDevice:
            return
        self.dragItem = it
        evt.Allow ()
    
    def OnEndDrag (self, evt):
        
        """Drag-and-drop callback: drop."""
        
        moved_device = self.dragItem
        
        if moved_device == None:
            #someone tried to drag a master device
            return
        
        if evt.GetItem ().IsOk ():
            
            target_menuitem = evt.GetItem ()
            target_device = self.GetItemPyData (target_menuitem)
            # If the user dragged one slave onto another slave, he probably
            # meant to drag it onto a master device.
            if target_device.__class__ == SlaveDevice:
                target_menuitem = self.GetItemParent (target_menuitem)
                target_device = self.GetItemPyData (target_menuitem)
                
            # Generate the pending commands for this action
            self.UI.changes.MoveDeviceCmd (moved_device, target_device)
        
        else:
            
            # assume it was dragged past the bottom of the list, and interpret
            # this as a detach
            self.UI.changes.DetachDeviceCmd (moved_device)
        
    
    def OnCollapseOrExpandItem (self, evt):
        
        """Item collapse/expand callback
        
        Since the widgets in this list are regenerated willy-nilly, we need a
        way to persistently track which have been collapsed.
        
        """
        
        if evt.GetItem ().IsOk ():
            expanded = self.IsExpanded (evt.GetItem ())
            self.GetItemPyData (evt.GetItem ()).expanded = expanded
    
    def OnSelectItem (self, evt):
        
        """Selection callback: select an item in the list.
        
        Updates the contents of the right-click menu in case the item is going
        to be right-clicked. Also update the main toolbar so its buttons will
        act on the currently selected item.
        
        """
        
        self.selection_context = None
        self.delete_callback = None
        self.UI.vbox.toolbar.button_del.Enable (False)
        
        if evt.GetItem ().IsOk ():
            target = evt.GetItem ()
        else:
            return
        
        target_device = self.GetItemPyData(target)
        
        if target_device != None:
            self.selection_context = ctx_menu = wx.Menu ()
            self.UI.changes.MakeUndoMenuItem (ctx_menu, target_device)
            self.delete_callback = self.UI.changes.MakeDeleteMenuItem (ctx_menu, target_device)
            self.UI.changes.MakeMasterDeviceMenuItems (ctx_menu, target_device)
            
            if self.delete_callback != None:
                self.UI.vbox.toolbar.button_del.Enable (True)
        
    def OnRightClick (self, evt):
        
        """Right-click callback: update selection, display context menu."""
        
        if evt.GetItem ().IsOk ():
            target = evt.GetItem ()
        else:
            return
        
        self.SelectItem (target)
        
        if self.selection_context != None:
            self.PopupMenu (self.selection_context)

class MainBar (wx.Panel):
    
    """The main toolbar."""
    
    def __init__ (self, parent, panel):
        
        super (MainBar, self).__init__(panel)
        
        self.changes = parent.UI.changes
        self.parent = parent
        
        sizer = wx.BoxSizer (wx.HORIZONTAL)
        
        button_refresh = wx.Button (self, label='Refresh', id = wx.ID_REFRESH)
        refresh_tooltip = wx.ToolTip ("Abandon changes and reload device list")
        button_refresh.SetToolTip (refresh_tooltip)
        sizer.Add (button_refresh)
        self.Bind (wx.EVT_BUTTON, self.OnRefresh, button_refresh)
        
        self.button_apply = wx.Button (self, label='Apply', id = wx.ID_APPLY)
        self.button_apply.Enable (False)
        apply_tooltip = wx.ToolTip ("Apply pending changes")
        self.button_apply.SetToolTip (apply_tooltip)
        sizer.Add (self.button_apply)
        self.Bind (wx.EVT_BUTTON, self.OnApply, self.button_apply)
        
        button_new = wx.Button (self, label='Add', id = wx.ID_ADD)
        new_tooltip = wx.ToolTip ("Add a new master device")
        button_new.SetToolTip (new_tooltip)
        sizer.Add (button_new)
        self.Bind (wx.EVT_BUTTON, self.OnNewMasterStart, button_new)
        
        self.button_del = wx.Button (self, label='Remove', id = wx.ID_REMOVE)
        self.button_del.Enable (False)
        sizer.Add (self.button_del)
        self.Bind (wx.EVT_BUTTON, self.OnDelete, self.button_del)
        
        self.SetSizer (sizer)
    
    def OnRefresh (self, _):
        
        self.changes.Reset ()
    
    def OnApply (self, _):
        
        self.changes.Apply ()
    
    def OnDelete (self, evt):
        
        self.parent.tree.delete_callback (evt)
    
    def OnNewMasterStart (self, _):
        
        self.parent.createmaster_toolbar.Show ()
        
class NewMasterBar (wx.Panel):
    
    """The toolbar used for adding new master pointers.
    
    This toolbar is normally hidden, but it appears when you click on "Add."
    It has a text field for editing the name of the master pointer which will
    be created, as well as "OK" and "Cancel" buttons.
    
    """
    
    def __init__ (self, parent, panel):
        
        self.parent = parent
        
        super (NewMasterBar, self).__init__(panel)
        
        sizer = wx.BoxSizer (wx.HORIZONTAL)
        
        label = wx.StaticText (self, label = "Name:")
        sizer.Add (label, flag = wx.ALIGN_CENTER)
        
        self.input = wx.TextCtrl (self, style = wx.TE_PROCESS_ENTER)
        sizer.Add (self.input, flag = wx.EXPAND, proportion = 1)
        self.Bind (wx.EVT_TEXT_ENTER, self.OnNewMasterDone, self.input)
        
        button_confirm = wx.Button (self, label='OK', style = wx.BU_EXACTFIT, id = wx.ID_OK)
        sizer.Add (button_confirm, flag = wx.ALIGN_RIGHT)
        self.Bind (wx.EVT_BUTTON, self.OnNewMasterDone, button_confirm)
        
        button_cancel = wx.Button (self, label='Cancel', style = wx.BU_EXACTFIT, id = wx.ID_CANCEL)
        sizer.Add (button_cancel, flag = wx.ALIGN_RIGHT)
        self.Bind (wx.EVT_BUTTON, self.OnCancel, button_cancel)
        
        self.SetSizer (sizer)
    
    def Show (self):
        
        """Make the toolbar visible, set default master pointer name."""
        
        self.parent.Show (self, True, True)
        
        self.input.SetValue ("New Pointer")
        self.input.SetSelection (0, -1)
        self.input.SetFocus()
        
        self.parent.Layout ()
    
    def Hide (self):
        
        """Make the toolbar invisible."""
    
        self.parent.Show (self, False, True)
        self.parent.Layout ()
    
    def OnCancel (self, _):
        self.Hide ()
    
    def OnNewMasterDone (self, _):
        
        newdevice = PendingDevice (self.input.GetValue ())
        self.Hide ()
        
        self.parent.changes.CreateDeviceCmd (newdevice)

class CommandList (wx.ListCtrl):
    
    """Widget listing the "xinput" commands corresponding to pending changes.
    
    This widget is not interactive in any way, apart from being scrollable.
    
    """
    
    def __init__ (self, window, panel):
        
        self.window = window
        
        # set up the GUI command list preview widget
        
        label = wx.StaticBox (panel, label = "Pending Commands:")
        sizer = wx.StaticBoxSizer (label, wx.VERTICAL)
        
        super (CommandList, self).__init__(panel, style = wx.LC_REPORT | wx.SUNKEN_BORDER | wx.LC_NO_HEADER)
        self.InsertColumn (0, "Commands", width = 250)
        sizer.Add (self, flag = wx.EXPAND, proportion = 1)
        
        panel.SetMinSize ((-1, 50))
        
        panel.SetSizer (sizer)

class Changes:
    
    """Class for tracking, updating, and applying pending changes."""
    
    def __init__ (self, UI):
        
        self.UI = UI
        
        # Used for categorizing different types of commands. Call Regenerate
        # after updating any of these.
        self.all_moves = {}
        self.all_deletions = set()
        self.all_creations = set()
        
        # Will be fed one at a time to run_command function. Updated by 
        # Regenerate.
        self.all_commands = [] 
        
        # reflects what's currently on-screen (i.e. current state plus pending
        # changes.) Updated by Regenerate.
        self.display_heirarchy = None
        
        # Essentially the device heirarchy as it currently exists, before 
        # changes.
        self.master_devices = None
    
    def GetDeviceStatusText (self, device):
        
        """For use in the device tree view display."""
        
        if device in self.all_moves:
            return " (move pending)"
        elif device in self.all_creations:
            return " (pending)"
        elif device in self.all_deletions:
            return " (deleted)"
        else:
            return ""
    
    def Regenerate (self):
        
        """Regenerates the pending command list and displays the new commands.
        
        Also updates the preview of the new device heirarchy as it will exist
        after changes are applied.
        
        Called after a device is moved, floated, deleted, created, etc.
        
        """
        
        self.UI.vbox.cmdlist.DeleteAllItems ()
        self.UI.vbox.tree.DeleteAllItems ()
        
        self.all_commands = []
        self.display_heirarchy = {master: [] for master in self.master_devices.values()}
        
        def AppendCommand (arglist):
            
            self.all_commands += [arglist]
            #add widget
            self.UI.vbox.cmdlist.InsertStringItem (self.UI.vbox.cmdlist.GetItemCount(), " ".join (arglist))
        
        def AddToHeirarchy (device):
            
            if device in self.all_moves:
                dest_device = self.all_moves[device]
                self_id_str = str(device.self_id)
                if dest_device.self_id == FLOATING_ID:
                    # don't have to explicitly run a float command if the
                    # parent is being deleted; that happens automatically
                    if device.parent not in self.all_deletions:
                        AppendCommand (["xinput", "float", self_id_str])
                else:
                    AppendCommand (["xinput", "reattach", self_id_str, str(dest_device.pointer_id)])
                    AppendCommand (["xinput", "reattach", self_id_str, str(dest_device.keyboard_id)])
                self.display_heirarchy[self.all_moves[device]] += [device]
            else:
                self.display_heirarchy[device.parent] += [device]
        
        for master in device_sort (self.master_devices.values()):
            if master in self.all_deletions:
                AppendCommand (["xinput", "remove-master", str(master.self_id)])
            for slave in master.children:
                AddToHeirarchy (slave)
        
        for master in device_sort (self.master_devices.values()):
            if master.self_id != FLOATING_ID:
                self.UI.vbox.tree.addMaster (master, self.display_heirarchy[master])
        
        for pending in self.all_creations:
            AppendCommand (["xinput", "create-master", pending.name])
            self.UI.vbox.tree.addMaster (pending, [])
        
        floating_group = self.master_devices[FLOATING_ID]
        self.UI.vbox.tree.addMaster (floating_group, self.display_heirarchy[floating_group])
        
        self.UI.vbox.toolbar.button_apply.Enable (bool(len(self.all_commands)))
    
    def Apply (self):
        
        """Run pending commands, then load the new state of the X server."""
        
        for cmd in self.all_commands:
            subprocess.Popen (["/usr/bin/env"] + cmd)

        # suppress the "unapplied pending changes" warning.
        self.all_commands = [] 

        self.Reset ()
    
    def MoveDeviceCmd (self, moved_device, target_device):
        
        if target_device in self.all_creations:
            wx.MessageBox (
                'Cannot add input devices to a pending pointer! '+
                'Hit "Apply" first to finish creating pointer "'+
                target_device.name+'"', 'Error', wx.OK | wx.ICON_EXCLAMATION
            )
            return
        
        if target_device in self.all_deletions:
            wx.MessageBox (
                'Pointer "'+target_device.name+'" is pending deletion! '+
                'To cancel deletion of this pointer, right-click it and '+
                'select "Cancel delete."', 'Error', wx.OK | wx.ICON_EXCLAMATION
            )
            return 
        
        if moved_device.parent == target_device:
            # a normal drag-and-drop operation has coincidentally had the same
            # effect as an undo operation
            if moved_device not in self.all_moves:
                return # don't need to do anything
            self.all_moves.pop (moved_device, None)
        else:
            if moved_device in self.all_moves and self.all_moves[moved_device] == target_device:
                return #don't need to do anything
            self.all_moves.update ({moved_device: target_device})
        
        target_device.expanded = True
        
        self.Regenerate ()
    
    def DetachDeviceCmd (self, child_device):
        
        target_device = self.master_devices[FLOATING_ID]
        self.MoveDeviceCmd (child_device, target_device)
    
    def UndoMoveDeviceCmd (self, device):
        
        self.MoveDeviceCmd (device, device.parent)
    
    def CreateDeviceCmd (self, new_device):
        
        self.all_creations.add (new_device)
        self.Regenerate ()
    
    def UndoCreateDeviceCmd (self, device):
        
        self.all_creations.remove (device)
        self.Regenerate ()
    
    def DetachAllSlavesFromDeviceCmd (self, device):
        
        current_slave_list = self.display_heirarchy[device]
        for slave in current_slave_list:
            self.DetachDeviceCmd (slave)
    
    def ResetAllSlavesOfDeviceCmd (self, device):
        
        # First undo any devices that have been moved to this master 
        
        # can't modify and iterate through the contents of the device tree 
        # simultaneously, so we need to defer our modifications
        slaves_to_move = set()
        
        for slave in self.display_heirarchy[device]:
            if slave.parent != device:
                slaves_to_move.add (slave)
        
        for slave in slaves_to_move:
            self.UndoMoveDeviceCmd (slave)
        
        # Now undo any devices that have been moved away from this master
        
        for slave in device.children:
            self.UndoMoveDeviceCmd (slave)
    
    def DeleteDeviceCmd (self, device):
        
        self.DetachAllSlavesFromDeviceCmd (device)
        self.all_deletions.add (device)
        self.Regenerate ()
    
    def UndoDeleteDeviceCmd (self, device):
        
        self.all_deletions.remove (device)
        self.Regenerate ()
    
    def Reset (self):
    
        if len (self.all_commands):
            confirm = wx.MessageDialog (self.UI,
                    'You still have pending changes! These will be lost if '+
                    'you refresh the device list. Refresh anyway?',
                    'Proceed?', wx.YES_NO | wx.ICON_QUESTION
                )
            result = confirm.ShowModal ()
            confirm.Destroy ()
            if result == wx.ID_NO:
                return
        
        self.master_devices = get_device_status()
        self.all_moves = {}
        self.all_deletions = set()
        self.all_creations = set()
        
        self.Regenerate ()
    
    #FIXME: this is kinda tedious
    
    def MakeUndoMenuItem (self, menu, device):
        
        item = None
        text = None
        action = None
        
        if device in self.all_deletions:
            text = 'Cancel delete '+device.name
            action = lambda _: self.UndoDeleteDeviceCmd (device)
        
        elif device in self.all_creations:
            text = 'Cancel create pointer '+device.name
            action = lambda _: self.UndoCreateDeviceCmd (device)
        
        elif device in self.all_moves and device.parent not in self.all_deletions:
            if self.all_moves[device].self_id == FLOATING_ID:
                text = 'Cancel detach '+device.name
            else:
                text = 'Cancel reattach '+device.name
            action = lambda _: self.UndoMoveDeviceCmd (device)
        
        else:
            return
        
        item = wx.MenuItem(menu, wx.NewId(), text)
        menu.AppendItem (item)
        menu.Bind(wx.EVT_MENU, action, item)
    
    def MakeDeleteMenuItem (self, menu, device):
        
        item = None
        text = None
        action = None
        
        if device in self.all_deletions or device in self.all_creations or device.self_id == FLOATING_ID:
            return None
        
        elif device in self.master_devices.values():
            text = 'Delete '+device.name
            action = lambda _: self.DeleteDeviceCmd (device)
        
        elif device not in self.all_moves and device.parent.self_id == FLOATING_ID:
            return None
        
        elif device in self.all_moves and self.all_moves[device].self_id == FLOATING_ID:
            return None
        
        else:
            text = 'Detach '+device.name
            action = lambda _: self.DetachDeviceCmd (device)
        
        item = wx.MenuItem(menu, wx.NewId(), text)
        menu.AppendItem (item)
        menu.Bind(wx.EVT_MENU, action, item)
        
        return action
    
    def MakeMasterDeviceMenuItems (self, menu, device):
        
        if      device not in self.master_devices.values() or \
                device in self.all_creations or \
                device in self.all_deletions or \
                device.self_id == FLOATING_ID:
            return
        
        reset_action = lambda _: self.ResetAllSlavesOfDeviceCmd (device)
        reset = wx.MenuItem (menu, wx.NewId(), 'Reset all devices for '+device.name)
        menu.AppendItem (reset)
        menu.Bind (wx.EVT_MENU, reset_action, reset)
        
        detach_all_action = lambda _: self.DetachAllSlavesFromDeviceCmd (device)
        detach_all = wx.MenuItem (menu, wx.NewId(), 'Detatch all devices from '+device.name)
        menu.AppendItem (detach_all)
        menu.Bind (wx.EVT_MENU, detach_all_action, detach_all)

class MainColumn (wx.BoxSizer):
    
    """Container widget containing all the other widgets in the GUI.
    
    Not much interesting functionality here, just layout stuff and a couple of
    callbacks. Should probably be merged with UI class below.
    
    """
        
    def __init__ (self, UI):
        
        self.UI = UI
        
        panel = wx.Panel (self.UI)
        
        super (MainColumn, self).__init__(wx.VERTICAL)
        
        splitter = wx.SplitterWindow (panel, -1)
        
        cmdpanel = wx.Panel (splitter)
        self.cmdlist = CommandList (self, cmdpanel)
        treepanel = wx.Panel (splitter)
        self.tree = DeviceTree (UI, treepanel)
        
        splitter.SplitHorizontally (treepanel, cmdpanel)
        splitter.SetSashGravity (1.0)
        splitter.SetSashPosition (-100)
        
        self.toolbar = MainBar (self, panel)
        self.createmaster_toolbar = NewMasterBar (self, panel)
        
        self.Add (self.toolbar, flag = wx.ALIGN_TOP)
        self.Add (self.createmaster_toolbar, proportion = 0, flag = wx.ALIGN_TOP | wx.EXPAND)
        self.createmaster_toolbar.Hide ()
        self.Add (splitter, flag = wx.EXPAND, proportion = 1)
        
        panel.SetSizer (self)
        
class UI (wx.Frame):
    
    """Top-level window widget.
    
    Besides some initialization code, there's not much interesting
    functionality here.  Just layout stuff and a couple of callbacks.
    
    """
    
    def __init__(self, parent, title):
    
        super(UI, self).__init__(parent, title = title, size = (400, 500))
        
        self.SetMinSize ((340, 150))
        
        self.changes = Changes (self)
        
        self.vbox = MainColumn (self)
        
        self.changes.Reset ()
        
        self.Show ()

app = wx.App()
UI(None, title = 'Xinput-UI')
app.MainLoop()

 
