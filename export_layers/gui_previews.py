#
# This file is part of Export Layers.
#
# Copyright (C) 2013-2016 khalim19 <khalim19@gmail.com>
#
# Export Layers is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Export Layers is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Export Layers.  If not, see <http://www.gnu.org/licenses/>.
#

"""
This module defines preview widgets used in the plug-in.
"""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

str = unicode

import array
import collections
import contextlib
import os

import pygtk
pygtk.require("2.0")
import gtk
import gobject
import pango

import gimp
import gimpenums

pdb = gimp.pdb

import export_layers.pygimplib as pygimplib

from export_layers.pygimplib import constants

from export_layers import exportlayers

#===============================================================================


class ExportPreview(object):
  
  def __init__(self):
    self._update_locked = False
    self._lock_keys = set()
    
    self._settings_events_to_temporarily_disable = {}
  
  def update(self, should_enable_sensitive=False):
    """
    Update the export preview if update is not locked (see `lock_update`).
    
    If `should_enable_sensitive` is True, set the sensitive state of the preview
    to True. Unlike `set_sensitive`, setting the sensitive state is performed
    only if the update is not locked.
    """
    
    pass
  
  def set_sensitive(self, sensitive):
    """
    Set the sensitivity of the preview (True = sensitive, False = insensitive).
    """
    
    pass
  
  def lock_update(self, lock, key=None):
    """
    If `lock` is True, calling `update` will have no effect. Passing False to
    `lock` will enable updating the preview again.
    
    If `key` is specified to lock the update, the same key must be specified to
    unlock the preview. Multiple keys can be used to lock the preview; to unlock
    the preview, call this method with each of the keys.
    
    If `key` is specified and `lock` is False and the key was not used to lock
    the preview before, nothing happens.
    
    If `key` is None, lock/unlock the preview regardless of which function
    called this method. Passing None also removes previous keys that were used
    to lock the preview.
    """
    
    if key is None:
      self._lock_keys.clear()
      self._update_locked = lock
    else:
      if lock:
        self._lock_keys.add(key)
      else:
        if key in self._lock_keys:
          self._lock_keys.remove(key)
      
      self._update_locked = bool(self._lock_keys)
  
  def temporarily_disable_setting_events_on_update(self, settings_and_event_ids):
    self._settings_events_to_temporarily_disable = settings_and_event_ids
  

#===============================================================================


class ExportNamePreview(ExportPreview):
  
  _VBOX_PADDING = 5
  _ADD_TAG_POPUP_HBOX_SPACING = 5
  _ADD_TAG_POPUP_BORDER_WIDTH = 5
  
  _COLUMNS = (
    _COLUMN_ICON_LAYER, _COLUMN_ICON_TAG_VISIBLE, _COLUMN_LAYER_NAME_SENSITIVE, _COLUMN_LAYER_NAME,
    _COLUMN_LAYER_ID) = ([0, gtk.gdk.Pixbuf], [1, bool], [2, bool], [3, bytes], [4, int])
  
  _ICON_IMAGE_PATH = os.path.join(pygimplib.config.PLUGIN_PATH, "icon_image.png")
  _ICON_TAG_PATH = os.path.join(pygimplib.config.PLUGIN_PATH, "icon_tag.png")
  
  def __init__(self, layer_exporter, initial_layer_tree=None, collapsed_items=None,
               selected_items=None, displayed_tags_setting=None, on_selection_changed_func=None,
               on_after_update_func=None, on_after_edit_tags_func=None):
    super(ExportNamePreview, self).__init__()
    
    self._layer_exporter = layer_exporter
    self._initial_layer_tree = initial_layer_tree
    self._collapsed_items = collapsed_items if collapsed_items is not None else set()
    self._selected_items = selected_items if selected_items is not None else []
    self._displayed_tags_setting = displayed_tags_setting
    self._on_selection_changed_func = (
      on_selection_changed_func if on_selection_changed_func is not None else lambda *args: None)
    self._on_after_update_func = on_after_update_func if on_after_update_func is not None else lambda *args: None
    self._on_after_edit_tags_func = (
      on_after_edit_tags_func if on_after_edit_tags_func is not None else lambda *args: None)
    
    self._tree_iters = collections.defaultdict(lambda: None)
    
    self._row_expand_collapse_interactive = True
    self._toggle_tag_interactive = True
    self._clearing_preview = False
    self._row_select_interactive = True
    self._initial_scroll_to_selection = True
    
    self._init_gui()
    
    self._widget = self._vbox
  
  def update(self, should_enable_sensitive=False, reset_items=False, update_existing_contents_only=False):
    """
    Update the preview (filter layers, modify layer tree, etc.).
    
    If `reset_items` is True, perform full update - add new layers, remove
    non-existent layers, etc. Note that setting this to True may introduce a
    performance penalty for hundreds of items.
    
    If `update_existing_contents_only` is True, only update the contents of the
    existing items. Note that the items will not be reparented,
    expanded/collapsed or added/removed even if they need to be. This option is
    useful if you know the item structure will be preserved.
    """
    
    if self._update_locked:
      return
    
    if should_enable_sensitive:
      self.set_sensitive(True)
    
    if not update_existing_contents_only:
      self.clear()
    
    self._process_items(reset_items=reset_items)
    
    self._enable_filtered_items(enabled=True)
    
    if not update_existing_contents_only:
      self._insert_items()
      self._set_expanded_items()
    else:
      self._update_items()
    
    self._set_selection()
    self._set_items_sensitive()
    
    self._enable_filtered_items(enabled=False)
    
    self._update_displayed_tags()
    
    self._tree_view.columns_autosize()
    
    self._on_after_update_func()
  
  def clear(self):
    """
    Clear the entire preview.
    """
    
    self._clearing_preview = True
    self._tree_model.clear()
    self._tree_iters.clear()
    self._clearing_preview = False
  
  def set_sensitive(self, sensitive):
    self._widget.set_sensitive(sensitive)
  
  def set_collapsed_items(self, collapsed_items):
    """
    Set the collapsed state of items in the preview.
    """
    
    self._collapsed_items = collapsed_items
    self._set_expanded_items()
  
  def set_selected_items(self, selected_items):
    """
    Set the selection of items in the preview.
    """
    
    self._selected_items = selected_items
    self._set_selection()
  
  def get_layer_elems_from_selected_rows(self):
    return [self._layer_exporter.layer_tree[layer_id]
            for layer_id in self._get_layer_ids_in_current_selection()]
  
  def get_layer_elem_from_cursor(self):
    tree_path, _unused = self._tree_view.get_cursor()
    if tree_path is not None:
      layer_id = self._get_layer_id(self._tree_model.get_iter(tree_path))
      return self._layer_exporter.layer_tree[layer_id]
    else:
      return None
  
  @property
  def widget(self):
    return self._widget
  
  @property
  def tree_view(self):
    return self._tree_view
  
  @property
  def collapsed_items(self):
    return self._collapsed_items
  
  @property
  def selected_items(self):
    return self._selected_items
  
  def _init_gui(self):
    self._tree_model = gtk.TreeStore(*[column[1] for column in self._COLUMNS])
    
    self._tree_view = gtk.TreeView(model=self._tree_model)
    self._tree_view.set_headers_visible(False)
    self._tree_view.set_enable_search(False)
    self._tree_view.get_selection().set_mode(gtk.SELECTION_MULTIPLE)
    
    self._init_icons()
    
    self._init_tags_menu()
    
    column = gtk.TreeViewColumn(b"")
    
    cell_renderer_icon_layer = gtk.CellRendererPixbuf()
    column.pack_start(cell_renderer_icon_layer, expand=False)
    column.set_attributes(cell_renderer_icon_layer, pixbuf=self._COLUMN_ICON_LAYER[0])
    
    cell_renderer_icon_tag = gtk.CellRendererPixbuf()
    cell_renderer_icon_tag.set_property("pixbuf", self._icons['tag'])
    column.pack_start(cell_renderer_icon_tag, expand=False)
    column.set_attributes(cell_renderer_icon_tag, visible=self._COLUMN_ICON_TAG_VISIBLE[0])
    
    cell_renderer_layer_name = gtk.CellRendererText()
    column.pack_start(cell_renderer_layer_name, expand=False)
    column.set_attributes(
      cell_renderer_layer_name, text=self._COLUMN_LAYER_NAME[0], sensitive=self._COLUMN_LAYER_NAME_SENSITIVE[0])
    
    self._tree_view.append_column(column)
    
    self._preview_label = gtk.Label(_("Preview"))
    self._preview_label.set_alignment(0.02, 0.5)
    
    self._scrolled_window = gtk.ScrolledWindow()
    self._scrolled_window.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
    self._scrolled_window.add(self._tree_view)
    
    self._vbox = gtk.VBox(homogeneous=False)
    self._vbox.pack_start(self._preview_label, expand=False, fill=False, padding=self._VBOX_PADDING)
    self._vbox.pack_start(self._scrolled_window)
    
    self._tree_view.connect("row-collapsed", self._on_tree_view_row_collapsed)
    self._tree_view.connect("row-expanded", self._on_tree_view_row_expanded)
    self._tree_view.get_selection().connect("changed", self._on_tree_selection_changed)
    self._tree_view.connect("event", self._on_tree_view_right_button_press)
  
  def _init_icons(self):
    self._icons = {}
    self._icons['layer_group'] = self._tree_view.render_icon(gtk.STOCK_DIRECTORY, gtk.ICON_SIZE_MENU)
    self._icons['layer'] = gtk.gdk.pixbuf_new_from_file_at_size(
      self._ICON_IMAGE_PATH, -1, self._icons['layer_group'].props.height)
    self._icons['tag'] = gtk.gdk.pixbuf_new_from_file_at_size(
      self._ICON_TAG_PATH, -1, self._icons['layer_group'].props.height)
    
    self._icons['merged_layer_group'] = self._icons['layer'].copy()
    
    scaling_factor = 0.8
    width_unscaled = self._icons['layer_group'].props.width
    width = int(width_unscaled * scaling_factor)
    height_unscaled = self._icons['layer_group'].props.height
    height = int(height_unscaled * scaling_factor)
    x_offset_unscaled = self._icons['merged_layer_group'].props.width - self._icons['layer_group'].props.width
    x_offset = x_offset_unscaled + width_unscaled - width
    y_offset_unscaled = self._icons['merged_layer_group'].props.height - self._icons['layer_group'].props.height
    y_offset = y_offset_unscaled + height_unscaled - height
    
    self._icons['layer_group'].composite(self._icons['merged_layer_group'],
      x_offset, y_offset, width, height, x_offset, y_offset,
      scaling_factor, scaling_factor, gtk.gdk.INTERP_BILINEAR, 255)
  
  def _init_tags_menu(self):
    self._tags_menu_items = {}
    self._tags_remove_submenu_items = {}
    
    self._tags_menu_relative_position = None
    
    self._tags_menu = gtk.Menu()
    self._tags_remove_submenu = gtk.Menu()
    
    self._tags_menu.append(gtk.SeparatorMenuItem())
    
    self._menu_item_add_tag = gtk.MenuItem(_("Add tag..."))
    self._menu_item_add_tag.connect("activate", self._on_tags_menu_item_add_tag_activate)
    self._tags_menu.append(self._menu_item_add_tag)
    
    self._menu_item_remove_tag = gtk.MenuItem(_("Remove tag"))
    self._menu_item_remove_tag.set_submenu(self._tags_remove_submenu)
    self._tags_menu.append(self._menu_item_remove_tag)
    
    for tag, tag_display_name in self._displayed_tags_setting.default_value.items():
      self._add_tag_menu_item(tag, tag_display_name)
    
    self._tags_menu.show_all()
  
  def _update_displayed_tags(self):
    self._layer_exporter.layer_tree.is_filtered = False
    
    used_tags = set()
    for layer_elem in self._layer_exporter.layer_tree:
      for tag in layer_elem.tags:
        used_tags.add(tag)
        if tag not in self._tags_menu_items:
          self._add_tag_menu_item(tag, tag)
          self._add_remove_tag_menu_item(tag, tag)
    
    self._layer_exporter.layer_tree.is_filtered = True
    
    for tag, menu_item in self._tags_remove_submenu_items.items():
      menu_item.set_sensitive(tag not in used_tags)
    
    for tag in self._displayed_tags_setting.value:
      if tag not in self._tags_menu_items:
        self._add_tag_menu_item(tag, tag)
        self._add_remove_tag_menu_item(tag, tag)
    
    self._menu_item_remove_tag.set_sensitive(bool(self._tags_remove_submenu.get_children()))
    
    self._sort_tags_menu_items()
    
    for tag in self._tags_menu_items:
      if tag not in self._displayed_tags_setting.value:
        self._displayed_tags_setting.value[tag] = tag
    
    self._displayed_tags_setting.save()
  
  def _sort_tags_menu_items(self):
    for new_tag_position, tag in enumerate(sorted(self._tags_menu_items, key=lambda tag: tag.lower())):
      self._tags_menu.reorder_child(self._tags_menu_items[tag], new_tag_position)
      if tag in self._tags_remove_submenu_items:
        self._tags_remove_submenu.reorder_child(self._tags_remove_submenu_items[tag], new_tag_position)
  
  def _add_tag_menu_item(self, tag, tag_display_name):
    self._tags_menu_items[tag] = gtk.CheckMenuItem(tag_display_name)
    self._tags_menu_items[tag].connect("toggled", self._on_tags_menu_item_toggled, tag)
    self._tags_menu_items[tag].show()
    self._tags_menu.prepend(self._tags_menu_items[tag])
  
  def _add_remove_tag_menu_item(self, tag, tag_display_name):
    self._tags_remove_submenu_items[tag] = gtk.MenuItem(tag_display_name)
    self._tags_remove_submenu_items[tag].connect("activate", self._on_tags_remove_submenu_item_activate, tag)
    self._tags_remove_submenu_items[tag].show()
    self._tags_remove_submenu.prepend(self._tags_remove_submenu_items[tag])
  
  def _on_tree_view_right_button_press(self, widget, event):
    if event.type == gtk.gdk.BUTTON_PRESS and event.button == 3:
      layer_ids = []
      stop_event_propagation = False
      
      # Get the current selection. We can't use `TreeSelection.get_selection()`
      # because this event is fired before the selection is updated.
      selection_at_pos = self._tree_view.get_path_at_pos(int(event.x), int(event.y))
      
      if selection_at_pos is not None and self._tree_view.get_selection().count_selected_rows() > 1:
        layer_ids = self._get_layer_ids_in_current_selection()
        stop_event_propagation = True
      else:
        if selection_at_pos is not None:
          tree_iter = self._tree_model.get_iter(selection_at_pos[0])
          layer_ids = [self._get_layer_id(tree_iter)]
      
      self._toggle_tag_interactive = False
      
      layer_elems = [self._layer_exporter.layer_tree[layer_id] for layer_id in layer_ids]
      for tag, tags_menu_item in self._tags_menu_items.items():
        tags_menu_item.set_active(all(tag in layer_elem.tags for layer_elem in layer_elems))
      
      self._toggle_tag_interactive = True
      
      if len(layer_ids) >= 1:
        self._tags_menu.popup(None, None, None, event.button, event.time)
        
        toplevel_widget = self._widget.get_toplevel()
        if toplevel_widget.flags() & gtk.TOPLEVEL:
          self._tags_menu_relative_position = toplevel_widget.get_window().get_pointer()
      
      return stop_event_propagation
  
  def _on_tags_menu_item_toggled(self, tags_menu_item, tag):
    if self._toggle_tag_interactive:
      pdb.gimp_image_undo_group_start(self._layer_exporter.image)
      
      for layer_id in self._get_layer_ids_in_current_selection():
        layer_elem = self._layer_exporter.layer_tree[layer_id]
        
        if tags_menu_item.get_active():
          layer_elem.add_tag(tag)
        else:
          layer_elem.remove_tag(tag)
      
      pdb.gimp_image_undo_group_end(self._layer_exporter.image)
      
      # Modifying just one layer could result in renaming other layers differently,
      # hence update the whole preview.
      self.update(update_existing_contents_only=True)
      
      self._on_after_edit_tags_func()
  
  def _on_tags_menu_item_add_tag_activate(self, menu_item_add_tag):
    def _on_popup_focus_out_event(popup, event):
      popup.destroy()
    
    def _on_popup_key_press_event(popup, event):
      key_name = gtk.gdk.keyval_name(event.keyval)
      if key_name in ["Return", "KP_Enter"]:
        entry_text = entry_add_tag.get_text()
        if entry_text and entry_text not in self._tags_menu_items:
          self._add_tag_menu_item(entry_text, entry_text)
          self._add_remove_tag_menu_item(entry_text, entry_text)
        
        popup.destroy()
        return True
      elif key_name == "Escape":
        popup.destroy()
        return True
    
    def _set_popup_position(popup, window):
      if self._tags_menu_relative_position is not None:
        window_absolute_position = window.get_window().get_origin()
        popup.move(
          window_absolute_position[0] + self._tags_menu_relative_position[0],
          window_absolute_position[1] + self._tags_menu_relative_position[1])
        
        self._tags_menu_relative_position = None
    
    popup_add_tag = gtk.Window(gtk.WINDOW_TOPLEVEL)
    popup_add_tag.set_decorated(False)
    popup_add_tag.set_type_hint(gtk.gdk.WINDOW_TYPE_HINT_POPUP_MENU)
    
    toplevel_widget = self._widget.get_toplevel()
    if toplevel_widget.flags() & gtk.TOPLEVEL:
      popup_add_tag.set_transient_for(toplevel_widget)
    
    _set_popup_position(popup_add_tag, toplevel_widget)
    
    label_tag_name = gtk.Label(_("Tag name:"))
    
    entry_add_tag = gtk.Entry()
    
    hbox = gtk.HBox()
    hbox.set_spacing(self._ADD_TAG_POPUP_HBOX_SPACING)
    hbox.pack_start(label_tag_name, expand=False, fill=False)
    hbox.pack_start(entry_add_tag, expand=False, fill=False)
    hbox.set_border_width(self._ADD_TAG_POPUP_BORDER_WIDTH)
    
    frame = gtk.Frame()
    frame.add(hbox)
    
    popup_add_tag.add(frame)
    
    popup_add_tag.connect("focus-out-event", _on_popup_focus_out_event)
    popup_add_tag.connect("key-press-event", _on_popup_key_press_event)
    
    popup_add_tag.show_all()
  
  def _on_tags_remove_submenu_item_activate(self, tags_remove_submenu_item, tag):
    self._tags_remove_submenu.remove(tags_remove_submenu_item)
    self._tags_menu.remove(self._tags_menu_items[tag])
    
    del self._tags_menu_items[tag]
    del self._tags_remove_submenu_items[tag]
    del self._displayed_tags_setting.value[tag]
    
    self._menu_item_remove_tag.set_sensitive(bool(self._tags_remove_submenu.get_children()))
    
    self._displayed_tags_setting.save()
  
  def _on_tree_view_row_collapsed(self, widget, tree_iter, tree_path):
    if self._row_expand_collapse_interactive:
      self._collapsed_items.add(self._get_layer_id(tree_iter))
      self._tree_view.columns_autosize()
  
  def _on_tree_view_row_expanded(self, widget, tree_iter, tree_path):
    if self._row_expand_collapse_interactive:
      layer_id = self._get_layer_id(tree_iter)
      if layer_id in self._collapsed_items:
        self._collapsed_items.remove(layer_id)
      
      self._set_expanded_items(tree_path)
      
      self._tree_view.columns_autosize()
  
  def _on_tree_selection_changed(self, widget):
    if not self._clearing_preview and self._row_select_interactive:
      previous_selected_items = self._selected_items
      self._selected_items = self._get_layer_ids_in_current_selection()
      
      if self._layer_exporter.export_settings['export_only_selected_layers'].value:
        if self._selected_items != previous_selected_items:
          self.update(update_existing_contents_only=True)
      
      self._on_selection_changed_func()
  
  def _get_layer_ids_in_current_selection(self):
    _unused, tree_paths = self._tree_view.get_selection().get_selected_rows()
    return [self._get_layer_id(self._tree_model.get_iter(tree_path)) for tree_path in tree_paths]
  
  def _get_layer_id(self, tree_iter):
    return self._tree_model.get_value(tree_iter, column=self._COLUMN_LAYER_ID[0])
  
  def _process_items(self, reset_items=False):
    if not reset_items:
      if self._initial_layer_tree is not None:
        layer_tree = self._initial_layer_tree
        self._initial_layer_tree = None
      else:
        if self._layer_exporter.layer_tree is not None:
          self._layer_exporter.layer_tree.reset_item_elements()
        layer_tree = self._layer_exporter.layer_tree
    else:
      layer_tree = None
    
    with self._layer_exporter.modify_export_settings(
           {'selected_layers': {self._layer_exporter.image.ID: self._selected_items}},
           self._settings_events_to_temporarily_disable):
      self._layer_exporter.export_layers(operations=['layer_name'], layer_tree=layer_tree)
  
  def _update_items(self):
    for layer_elem in self._layer_exporter.layer_tree:
      if self._layer_exporter.export_settings['layer_groups_as_folders'].value:
        self._update_parent_item_elems(layer_elem)
      self._update_item_elem(layer_elem)
  
  def _insert_items(self):
    for layer_elem in self._layer_exporter.layer_tree:
      if self._layer_exporter.export_settings['layer_groups_as_folders'].value:
        self._insert_parent_item_elems(layer_elem)
      self._insert_item_elem(layer_elem)
  
  def _insert_item_elem(self, item_elem):
    if item_elem.parent:
      parent_tree_iter = self._tree_iters[item_elem.parent.item.ID]
    else:
      parent_tree_iter = None
    
    tree_iter = self._tree_model.append(
      parent_tree_iter,
      [self._get_icon_from_item_elem(item_elem),
       bool(item_elem.tags),
       True,
       item_elem.name.encode(constants.GTK_CHARACTER_ENCODING),
       item_elem.item.ID])
    self._tree_iters[item_elem.item.ID] = tree_iter
    
    return tree_iter
  
  def _update_item_elem(self, item_elem):
    self._tree_model.set(
      self._tree_iters[item_elem.item.ID],
      self._COLUMN_ICON_TAG_VISIBLE[0], bool(item_elem.tags),
      self._COLUMN_LAYER_NAME_SENSITIVE[0], True,
      self._COLUMN_LAYER_NAME[0], item_elem.name.encode(constants.GTK_CHARACTER_ENCODING))
  
  def _insert_parent_item_elems(self, item_elem):
    for parent_elem in item_elem.parents:
      if not self._tree_iters[parent_elem.item.ID]:
        self._insert_item_elem(parent_elem)
  
  def _update_parent_item_elems(self, item_elem):
    for parent_elem in item_elem.parents:
      self._update_item_elem(parent_elem)
  
  def _enable_filtered_items(self, enabled):
    if self._layer_exporter.export_settings['export_only_selected_layers'].value:
      if not enabled:
        self._layer_exporter.layer_tree.filter.add_rule(
          exportlayers.LayerFilterRules.is_layer_in_selected_layers, self._selected_items)
      else:
        self._layer_exporter.layer_tree.filter.remove_rule(
          exportlayers.LayerFilterRules.is_layer_in_selected_layers, raise_if_not_found=False)
    
    if self._layer_exporter.export_settings['process_tagged_layers'].value:
      if not enabled:
        self._layer_exporter.layer_tree.filter.add_rule(exportlayers.LayerFilterRules.has_no_tags)
      else:
        self._layer_exporter.layer_tree.filter.remove_rule(
          exportlayers.LayerFilterRules.has_no_tags, raise_if_not_found=False)
  
  def _set_items_sensitive(self):
    if self._layer_exporter.export_settings['export_only_selected_layers'].value:
      self._set_item_elems_sensitive(self._layer_exporter.layer_tree, False)
      self._set_item_elems_sensitive(
        [self._layer_exporter.layer_tree[item_id] for item_id in self._selected_items], True)
    
    if self._layer_exporter.export_settings['process_tagged_layers'].value:
      with self._layer_exporter.layer_tree.filter.add_rule_temp(exportlayers.LayerFilterRules.has_tags):
        self._set_item_elems_sensitive(self._layer_exporter.layer_tree, False)
        
        if self._layer_exporter.export_settings['layer_groups_as_folders'].value:
          with self._layer_exporter.layer_tree.filter['layer_types'].add_rule_temp(
                 exportlayers.LayerFilterRules.is_nonempty_group), \
               self._layer_exporter.layer_tree.filter['layer_types'].remove_rule_temp(
                 exportlayers.LayerFilterRules.is_layer):
            for layer_elem in self._layer_exporter.layer_tree:
              self._set_item_elem_sensitive(layer_elem, False)
  
  def _get_item_elem_sensitive(self, item_elem):
    return self._tree_model.get_value(self._tree_iters[item_elem.item.ID], self._COLUMN_LAYER_NAME_SENSITIVE[0])
  
  def _set_item_elem_sensitive(self, item_elem, sensitive):
    if self._tree_iters[item_elem.item.ID] is not None:
      self._tree_model.set_value(
        self._tree_iters[item_elem.item.ID], self._COLUMN_LAYER_NAME_SENSITIVE[0], sensitive)
  
  def _set_parent_item_elems_sensitive(self, item_elem):
    for parent_elem in reversed(list(item_elem.parents)):
      parent_sensitive = any(
        self._get_item_elem_sensitive(child_elem) for child_elem in parent_elem.children
        if child_elem.item.ID in self._tree_iters)
      self._set_item_elem_sensitive(parent_elem, parent_sensitive)
  
  def _set_item_elems_sensitive(self, item_elems, sensitive):
    for item_elem in item_elems:
      self._set_item_elem_sensitive(item_elem, sensitive)
      if self._layer_exporter.export_settings['layer_groups_as_folders'].value:
        self._set_parent_item_elems_sensitive(item_elem)
  
  def _get_icon_from_item_elem(self, item_elem):
    if item_elem.item_type == item_elem.ITEM:
      return self._icons['layer']
    elif item_elem.item_type in [item_elem.NONEMPTY_GROUP, item_elem.EMPTY_GROUP]:
      if not self._layer_exporter.export_settings['more_operations/merge_layer_groups'].value:
        return self._icons['layer_group']
      else:
        return self._icons['merged_layer_group']
    else:
      return None
  
  def _set_expanded_items(self, tree_path=None):
    """
    Set the expanded state of items in the tree view.
    
    If `tree_path` is specified, set the states only for the child elements in
    the tree path, otherwise set the states in the whole tree view.
    """
    
    self._row_expand_collapse_interactive = False
    
    if tree_path is None:
      self._tree_view.expand_all()
    else:
      self._tree_view.expand_row(tree_path, True)
    
    self._remove_no_longer_valid_collapsed_items()
    
    for layer_id in self._collapsed_items:
      if layer_id in self._tree_iters:
        layer_elem_tree_iter = self._tree_iters[layer_id]
        if layer_elem_tree_iter is None:
          continue
        
        layer_elem_tree_path = self._tree_model.get_path(layer_elem_tree_iter)
        if tree_path is None or self._tree_view.row_expanded(layer_elem_tree_path):
          self._tree_view.collapse_row(layer_elem_tree_path)
    
    self._row_expand_collapse_interactive = True
  
  def _remove_no_longer_valid_collapsed_items(self):
    if self._layer_exporter.layer_tree is None:
      return
    
    self._layer_exporter.layer_tree.is_filtered = False
    self._collapsed_items = set(
      [collapsed_item for collapsed_item in self._collapsed_items
       if collapsed_item in self._layer_exporter.layer_tree])
    self._layer_exporter.layer_tree.is_filtered = True
  
  def _set_selection(self):
    self._row_select_interactive = False
    
    self._selected_items = [item for item in self._selected_items if item in self._tree_iters]
    
    for item in self._selected_items:
      tree_iter = self._tree_iters[item]
      if tree_iter is not None:
        self._tree_view.get_selection().select_iter(tree_iter)
    
    if self._initial_scroll_to_selection:
      self._set_initial_scroll_to_selection()
      self._initial_scroll_to_selection = False
    
    self._row_select_interactive = True
  
  def _set_cursor(self, previous_cursor=None):
    self._row_select_interactive = False
    
    if previous_cursor is not None and self._tree_model.get_iter(previous_cursor) is not None:
      self._tree_view.set_cursor(previous_cursor)
    
    self._row_select_interactive = True
  
  def _set_initial_scroll_to_selection(self):
    if self._selected_items:
      first_selected_item_path = self._tree_model.get_path(self._tree_iters[self._selected_items[0]])
      if first_selected_item_path is not None:
        self._tree_view.scroll_to_cell(first_selected_item_path, None, True, 0.5, 0.0)


#===============================================================================


class ExportImagePreview(ExportPreview):
  
  _BOTTOM_WIDGETS_PADDING = 5
  _IMAGE_PREVIEW_PADDING = 3
  
  _MAX_PREVIEW_SIZE_PIXELS = 1024
  
  _PREVIEW_ALPHA_CHECK_SIZE = 4
  
  def __init__(self, layer_exporter, initial_layer_tree=None, initial_previered_layer_id=None):
    super(ExportImagePreview, self).__init__()
    
    self._layer_exporter = layer_exporter
    self._initial_layer_tree = initial_layer_tree
    self._initial_previewed_layer_id = initial_previered_layer_id
    
    self._layer_elem = None
    
    self._preview_pixbuf = None
    self._previous_preview_pixbuf_width = None
    self._previous_preview_pixbuf_height = None
    
    self.draw_checkboard_alpha_background = True
    
    self._is_updating = False
    
    self._preview_width = None
    self._preview_height = None
    self._preview_scaling_factor = None
    
    self._init_gui()
    
    self._PREVIEW_ALPHA_CHECK_COLOR_FIRST, self._PREVIEW_ALPHA_CHECK_COLOR_SECOND = (
      int(hex(shade)[2:] * 4, 16) for shade in gimp.checks_get_shades(gimp.check_type()))
    
    self._placeholder_image_size = gtk.icon_size_lookup(self._placeholder_image.get_property("icon-size"))
    
    self._vbox.connect("size-allocate", self._on_vbox_size_allocate)
    
    self._widget = self._vbox
  
  def update(self, should_enable_sensitive=False):
    if self._update_locked:
      return
    
    if should_enable_sensitive:
      self.set_sensitive(True)
    
    self.layer_elem = self._set_initial_layer_elem(self.layer_elem)
    if self.layer_elem is None:
      return
    
    if not self._layer_exporter.layer_tree.filter.is_match(self.layer_elem):
      self.layer_elem = None
      return
    
    if not pdb.gimp_item_is_valid(self.layer_elem.item):
      self.clear()
      return
    
    self._is_updating = True
    
    self._placeholder_image.hide()
    self._preview_image.show()
    self._set_layer_name_label(self.layer_elem.name)
    
    # Make sure that the correct size is allocated to the image.
    while gtk.events_pending():
      gtk.main_iteration()
    
    with self._redirect_messages():
      preview_pixbuf = self._get_in_memory_preview(self.layer_elem.item)
    
    if preview_pixbuf is not None:
      self._preview_image.set_from_pixbuf(preview_pixbuf)
    else:
      self.clear(use_layer_name=True)
    
    self._is_updating = False
  
  def clear(self, use_layer_name=False):
    self.layer_elem = None
    self._preview_image.clear()
    self._preview_image.hide()
    self._show_placeholder_image(use_layer_name)
  
  def set_sensitive(self, sensitive):
    self._widget.set_sensitive(sensitive)
  
  def resize(self, update_when_larger_than_image_size=False):
    """
    Resize the preview if the widget is smaller than the previewed image so that
    the image fits the widget.
    """
    
    if not self._is_updating and self._preview_image.get_mapped():
      self._resize_preview(self._preview_image.get_allocation(), self._preview_pixbuf)
  
  def is_larger_than_image(self):
    """
    Return True if the preview widget is larger than the image. If no image is
    previewed, return False.
    """
    
    allocation = self._preview_image.get_allocation()
    return (self._preview_pixbuf is not None and allocation.width > self._preview_pixbuf.get_width()
            and allocation.height > self._preview_pixbuf.get_height())
  
  def update_layer_elem(self):
    if (self.layer_elem is not None
        and self._layer_exporter.layer_tree is not None
        and self.layer_elem.item.ID in self._layer_exporter.layer_tree):
      layer_elem = self._layer_exporter.layer_tree[self.layer_elem.item.ID]
      if self._layer_exporter.layer_tree.filter.is_match(layer_elem):
        self.layer_elem = layer_elem
        self._set_layer_name_label(self.layer_elem.name)
  
  @property
  def layer_elem(self):
    return self._layer_elem
  
  @layer_elem.setter
  def layer_elem(self, value):
    self._layer_elem = value
    if value is None:
      self._preview_pixbuf = None
      self._previous_preview_pixbuf_width = None
      self._previous_preview_pixbuf_height = None
  
  @property
  def widget(self):
    return self._widget
  
  def _init_gui(self):
    self._preview_image = gtk.Image()
    self._preview_image.set_no_show_all(True)
    
    self._placeholder_image = gtk.Image()
    self._placeholder_image.set_from_stock(gtk.STOCK_DIALOG_QUESTION, gtk.ICON_SIZE_DIALOG)
    self._placeholder_image.set_no_show_all(True)
    
    self._label_layer_name = gtk.Label()
    self._label_layer_name.set_ellipsize(pango.ELLIPSIZE_MIDDLE)
    
    self._vbox = gtk.VBox(homogeneous=False)
    self._vbox.pack_start(self._preview_image, expand=True, fill=True, padding=self._IMAGE_PREVIEW_PADDING)
    self._vbox.pack_start(self._placeholder_image, expand=True, fill=True, padding=self._IMAGE_PREVIEW_PADDING)
    self._vbox.pack_start(self._label_layer_name, expand=False, fill=False, padding=self._BOTTOM_WIDGETS_PADDING)
    
    self._show_placeholder_image()
  
  def _set_initial_layer_elem(self, layer_elem):
    if layer_elem is None:
      if (self._layer_exporter.layer_tree is not None
          and self._initial_previewed_layer_id in self._layer_exporter.layer_tree):
        layer_elem = self._layer_exporter.layer_tree[self._initial_previewed_layer_id]
        self._initial_previewed_layer_id = None
        return layer_elem
      else:
        self._initial_previewed_layer_id = None
        return None
    else:
      return layer_elem
  
  def _get_in_memory_preview(self, layer):
    self._preview_width, self._preview_height = self._get_preview_size(layer.width, layer.height)
    self._preview_scaling_factor = self._preview_width / layer.width
    
    image_preview = self._get_image_preview()
    if image_preview is None:
      return None
    
    if image_preview.base_type != gimpenums.RGB:
      pdb.gimp_image_convert_rgb(image_preview)
    
    layer_preview = image_preview.layers[0]
    
    if layer_preview.mask is not None:
      layer_preview.remove_mask(gimpenums.MASK_APPLY)
    
    # The layer may have been resized during the export, hence recompute the size.
    self._preview_width, self._preview_height = self._get_preview_size(
      layer_preview.width, layer_preview.height)
    
    self._preview_width, self._preview_height, preview_data = self._get_preview_data(
      layer_preview, self._preview_width, self._preview_height)
    
    layer_preview_pixbuf = self._get_preview_pixbuf(
      layer_preview, self._preview_width, self._preview_height, preview_data)
    
    self._cleanup(image_preview)
    
    return layer_preview_pixbuf
  
  @contextlib.contextmanager
  def _redirect_messages(self, message_handler=gimpenums.ERROR_CONSOLE):
    orig_message_handler = pdb.gimp_message_get_handler()
    pdb.gimp_message_set_handler(message_handler)
    
    try:
      yield
    finally:
      pdb.gimp_message_set_handler(orig_message_handler)
  
  def _get_image_preview(self):
    if self._initial_layer_tree is not None:
      layer_tree = self._initial_layer_tree
      self._initial_layer_tree = None
    else:
      layer_tree = self._layer_exporter.layer_tree
    
    layer_tree_filter = layer_tree.filter if layer_tree is not None else None
    
    with self._layer_exporter.modify_export_settings(
           {'export_only_selected_layers': True,
            'selected_layers': {self._layer_exporter.image.ID: set([self.layer_elem.item.ID])}},
           self._settings_events_to_temporarily_disable):
      try:
        image_preview = self._layer_exporter.export_layers(
          operations=['layer_contents'], layer_tree=layer_tree, keep_exported_layers=True,
          on_after_create_image_copy_func=self._layer_exporter_on_after_create_image_copy,
          on_after_insert_layer_func=self._layer_exporter_on_after_insert_layer)
      except Exception:
        image_preview = None
    
    if layer_tree_filter is not None:
      self._layer_exporter.layer_tree.filter = layer_tree_filter
    
    return image_preview
  
  def _layer_exporter_on_after_create_image_copy(self, image_copy):
    pdb.gimp_image_resize(
      image_copy,
      max(1, int(round(image_copy.width * self._preview_scaling_factor))),
      max(1, int(round(image_copy.height * self._preview_scaling_factor))),
      0, 0)
    
    pdb.gimp_context_set_interpolation(gimpenums.INTERPOLATION_NONE)
  
  def _layer_exporter_on_after_insert_layer(self, layer):
    if not pdb.gimp_item_is_group(layer):
      pdb.gimp_layer_scale(
        layer,
        max(1, int(round(layer.width * self._preview_scaling_factor))),
        max(1, int(round(layer.height * self._preview_scaling_factor))),
        False)
  
  def _get_preview_pixbuf(self, layer, preview_width, preview_height, preview_data):
    # The following code is largely based on the implementation of `gimp_pixbuf_from_data`
    # from: https://github.com/GNOME/gimp/blob/gimp-2-8/libgimp/gimppixbuf.c
    layer_preview_pixbuf = gtk.gdk.pixbuf_new_from_data(
      preview_data, gtk.gdk.COLORSPACE_RGB, layer.has_alpha, 8, preview_width,
      preview_height, preview_width * layer.bpp)
    
    self._preview_pixbuf = layer_preview_pixbuf
    
    if layer.has_alpha:
      layer_preview_pixbuf = self._add_alpha_background_to_pixbuf(
        layer_preview_pixbuf, layer.opacity, self.draw_checkboard_alpha_background,
        self._PREVIEW_ALPHA_CHECK_SIZE,
        self._PREVIEW_ALPHA_CHECK_COLOR_FIRST, self._PREVIEW_ALPHA_CHECK_COLOR_SECOND)
    
    return layer_preview_pixbuf
  
  def _add_alpha_background_to_pixbuf(self, pixbuf, opacity, use_checkboard_background=False, check_size=None,
                                      check_color_first=None, check_color_second=None):
    if use_checkboard_background:
      pixbuf_with_alpha_background = gtk.gdk.Pixbuf(
        gtk.gdk.COLORSPACE_RGB, False, 8,
        pixbuf.get_width(), pixbuf.get_height())
      
      pixbuf.composite_color(
        pixbuf_with_alpha_background, 0, 0,
        pixbuf.get_width(), pixbuf.get_height(),
        0, 0, 1.0, 1.0, gtk.gdk.INTERP_NEAREST,
        int(round((opacity / 100.0) * 255)),
        0, 0, check_size, check_color_first, check_color_second)
    else:
      pixbuf_with_alpha_background = gtk.gdk.Pixbuf(
        gtk.gdk.COLORSPACE_RGB, True, 8,
        pixbuf.get_width(), pixbuf.get_height())
      pixbuf_with_alpha_background.fill(0xffffff00)
      
      pixbuf.composite(
        pixbuf_with_alpha_background, 0, 0,
        pixbuf.get_width(), pixbuf.get_height(),
        0, 0, 1.0, 1.0, gtk.gdk.INTERP_NEAREST,
        int(round((opacity / 100.0) * 255)))
    
    return pixbuf_with_alpha_background
  
  def _get_preview_data(self, layer, preview_width, preview_height):
    actual_preview_width, actual_preview_height, _unused, _unused, preview_data = (
      pdb.gimp_drawable_thumbnail(layer, preview_width, preview_height))
    
    return actual_preview_width, actual_preview_height, array.array(b"B", preview_data).tostring()
  
  def _get_preview_size(self, width, height):
    preview_widget_allocation = self._preview_image.get_allocation()
    preview_widget_width = preview_widget_allocation.width
    preview_widget_height = preview_widget_allocation.height
    
    if preview_widget_width > preview_widget_height:
      preview_height = min(preview_widget_height, height, self._MAX_PREVIEW_SIZE_PIXELS)
      preview_width = int(round((preview_height / height) * width))
      
      if preview_width > preview_widget_width:
        preview_width = preview_widget_width
        preview_height = int(round((preview_width / width) * height))
    else:
      preview_width = min(preview_widget_width, width, self._MAX_PREVIEW_SIZE_PIXELS)
      preview_height = int(round((preview_width / width) * height))
      
      if preview_height > preview_widget_height:
        preview_height = preview_widget_height
        preview_width = int(round((preview_height / height) * width))
    
    if preview_width == 0:
      preview_width = 1
    if preview_height == 0:
      preview_height = 1
    
    return preview_width, preview_height
  
  def _resize_preview(self, preview_allocation, preview_pixbuf):
    if preview_pixbuf is None:
      return
    
    if (preview_allocation.width >= preview_pixbuf.get_width()
        and preview_allocation.height >= preview_pixbuf.get_height()):
      return
    
    scaled_preview_width, scaled_preview_height = self._get_preview_size(
      preview_pixbuf.get_width(), preview_pixbuf.get_height())
    
    if (self._previous_preview_pixbuf_width == scaled_preview_width
        and self._previous_preview_pixbuf_height == scaled_preview_height):
      return
    
    scaled_preview_pixbuf = preview_pixbuf.scale_simple(
      scaled_preview_width, scaled_preview_height, gtk.gdk.INTERP_NEAREST)
    
    scaled_preview_pixbuf = self._add_alpha_background_to_pixbuf(
      scaled_preview_pixbuf, 100, self.draw_checkboard_alpha_background,
      self._PREVIEW_ALPHA_CHECK_SIZE,
      self._PREVIEW_ALPHA_CHECK_COLOR_FIRST, self._PREVIEW_ALPHA_CHECK_COLOR_SECOND)
    
    self._preview_image.set_from_pixbuf(scaled_preview_pixbuf)
    
    self._previous_preview_pixbuf_width = scaled_preview_width
    self._previous_preview_pixbuf_height = scaled_preview_height
  
  def _cleanup(self, image_preview):
    pdb.gimp_image_delete(image_preview)
  
  def _on_vbox_size_allocate(self, image_widget, allocation):
    if not self._is_updating and not self._preview_image.get_mapped():
      preview_widget_allocated_width = allocation.width - self._IMAGE_PREVIEW_PADDING * 2
      preview_widget_allocated_height = (
        allocation.height - self._label_layer_name.get_allocation().height
        - self._BOTTOM_WIDGETS_PADDING * 2 - self._IMAGE_PREVIEW_PADDING * 2)
      
      if (preview_widget_allocated_width < self._placeholder_image_size[0]
          or preview_widget_allocated_height < self._placeholder_image_size[1]):
        self._placeholder_image.hide()
      else:
        self._placeholder_image.show()
  
  def _show_placeholder_image(self, use_layer_name=False):
    self._placeholder_image.show()
    if not use_layer_name:
      self._set_layer_name_label(_("No selection"))
  
  def _set_layer_name_label(self, layer_name):
    self._label_layer_name.set_markup(
      "<i>{0}</i>".format(gobject.markup_escape_text(layer_name.encode(constants.GTK_CHARACTER_ENCODING))))
