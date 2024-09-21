# Copyright (c) 2018-2021, NVIDIA CORPORATION.  All rights reserved.
#
# NVIDIA CORPORATION and its licensors retain all intellectual property
# and proprietary rights in and to this software, related documentation
# and any modifications thereto.  Any use, reproduction, disclosure or
# distribution of this software and related documentation without an express
# license agreement from NVIDIA CORPORATION is strictly prohibited.
#
__all__ = ["export", "Export"]

import os
from typing import List, Set
from functools import partial
from pxr import Sdf, Gf, Usd, UsdGeom, UsdUI
from omni.kit.window.file_exporter import get_file_exporter
from omni.kit.helper.file_utils import FileEventModel, FILE_SAVED_EVENT

import carb
import carb.profiler
import carb.tokens
import omni.kit.app
import omni.client
import omni.usd


last_dir = None

# OM-48055: Add subscription to stage open to update default save directory
_default_save_dir = None

def __on_stage_open(event: carb.events.IEvent):
    """Update default save directory on stage open."""
    if event.type == int(omni.usd.StageEventType.OPENED):
        stage = omni.usd.get_context().get_stage()
        global _default_save_dir
        _default_save_dir = os.path.dirname(stage.GetRootLayer().realPath)

def _get_stage_open_sub():
    stage_open_sub = omni.usd.get_context().get_stage_event_stream().create_subscription_to_pop(__on_stage_open,
        name="Export Selected Prim Stage Open")
    return stage_open_sub


def __set_xform_prim_transform(prim: UsdGeom.Xformable, transform: Gf.Matrix4d):
    prim = UsdGeom.Xformable(prim)
    _, _, scale, rot_mat, translation, _ = transform.Factor()
    angles = rot_mat.ExtractRotation().Decompose(Gf.Vec3d.ZAxis(), Gf.Vec3d.YAxis(), Gf.Vec3d.XAxis())
    rotation = Gf.Vec3f(angles[2], angles[1], angles[0])

    for xform_op in prim.GetOrderedXformOps():
        attr = xform_op.GetAttr()
        prim.GetPrim().RemoveProperty(attr.GetName())
    prim.ClearXformOpOrder()

    UsdGeom.XformCommonAPI(prim).SetTranslate(translation)
    UsdGeom.XformCommonAPI(prim).SetRotate(rotation)
    UsdGeom.XformCommonAPI(prim).SetScale(Gf.Vec3f(scale[0], scale[1], scale[2]))


def _get_all_children(prim: Usd.Prim) -> Set[Usd.Prim]:
    """Utility function that gets all children of the given prim."""
    children_list = set([])
    queue = [prim]
    while len(queue) > 0:
        child_prim = queue.pop()
        for child in child_prim.GetAllChildren():
            children_list.add(child)
            queue.append(child)

    return children_list


def _duplicate_variant_sets(source_prim: Usd.Prim, target_prim: Usd.Prim):
    """Utility function that helps duplication of variant sets from the source prim to the target prim."""
    src_variant_sets = source_prim.GetVariantSets()
    if not src_variant_sets:
        return

    variant_set_names = src_variant_sets.GetNames()
    for variant_set_name in variant_set_names:
        # Get the current variant selection
        current_variant = src_variant_sets.GetVariantSelection(variant_set_name)
        target_variant_set = target_prim.GetVariantSets().AddVariantSet(variant_set_name)
        source_variant_set = src_variant_sets.GetVariantSet(variant_set_name)

        # Iterate over each variant in the source variant set
        for variant_name in source_variant_set.GetVariantNames():
            source_variant_set.SetVariantSelection(variant_name)
            with target_variant_set.GetVariantEditContext():
                Sdf.CopySpec(source_prim.GetStage().GetRootLayer(),
                             source_prim.GetPath(),
                             target_prim.GetStage().GetRootLayer(),
                             target_prim.GetPath())

        # Set the original variant selection back on the source prim and target prim
        source_variant_set.SetVariantSelection(current_variant)
        target_variant_set.SetVariantSelection(current_variant)


def _remove_duplicate_prims(prim_list: List[Usd.Prim], stage: Usd.Stage) -> List[Usd.Prim]:
    """
    Utility function that removes duplicated prims.
    For example, prims that are selected but are children of other selected prims are already included so can be removed.
    """
    src_paths = [prim.GetPath() for prim in prim_list]
    paths = Sdf.Path.RemoveDescendentPaths(src_paths)
    return [stage.GetPrimAtPath(p) for p in paths]


@carb.profiler.profile
def export(path: str, prims: List[Usd.Prim]):
    """
    Exports specified prims to an external USD file with the given path.
    If more than one prim is specified, the parent transforms will be exported automatically.

    Args:
        path (str): The target layer path.
        prims (List[Usd.Prim]): Prims to export.
    """
    stage = omni.usd.get_context().get_stage()

    # OM-87457: Fix issue with exporting duplicate prims when selected prims are parent-children prims
    prims = _remove_duplicate_prims(prims, stage)

    # OM-67884: Flatten layer stack then open masked stage before flattening the whole
    #  stage to improve performance
    from pxr import UsdUtils

    temp_flattened_layer = UsdUtils.FlattenLayerStack(stage)
    mask = [prim.GetPath() for prim in prims]
    masked_stage = Usd.Stage.OpenMasked(temp_flattened_layer, Usd.StagePopulationMask(mask))

    source_layer = masked_stage.Flatten()
    target_layer = Sdf.Layer.CreateNew(path)
    target_stage = Usd.Stage.Open(target_layer)
    axis = UsdGeom.GetStageUpAxis(stage)
    UsdGeom.SetStageUpAxis(target_stage, axis)

    # All prims will be put under /Root
    if len(prims) > 1:
        root_path = Sdf.Path.absoluteRootPath.AppendChild("Root")
        UsdGeom.Xform.Define(target_stage, root_path)
    else:
        root_path = Sdf.Path.absoluteRootPath
    keep_transforms = len(prims) > 1

    center_point = Gf.Vec3d(0.0)
    transforms = []
    if keep_transforms:
        bound_box = Gf.BBox3d()
        bbox_cache = UsdGeom.BBoxCache(Usd.TimeCode.Default(), includedPurposes=[UsdGeom.Tokens.default_])
        for prim in prims:
            xformable = UsdGeom.Xformable(prim)
            if xformable:
                local_bound_box = bbox_cache.ComputeWorldBound(prim)
                transforms.append(xformable.ComputeLocalToWorldTransform(Usd.TimeCode.Default()))
                bound_box = Gf.BBox3d.Combine(bound_box, local_bound_box)
            else:
                transforms.append(None)

        center_point = bound_box.ComputeCentroid()
    else:
        transforms.append(Gf.Matrix4d(1.0))

    for i in range(len(transforms)):
        if transforms[i]:
            transforms[i] = transforms[i].SetTranslateOnly(transforms[i].ExtractTranslation() - center_point)

    # Set default prim name
    # https://forums.developer.nvidia.com/t/export-usd-model-from-usd-composer-isaac-sim/258436
    if len(prims) > 1:
        target_layer.defaultPrim = root_path.name

        for i in range(len(prims)):
            source_path = prims[i].GetPath()
            if len(prims) > 1 and transforms[i]:
                target_xform_path = root_path.AppendChild(source_path.name)
                target_xform_path = Sdf.Path(omni.usd.get_stage_next_free_path(target_stage, target_xform_path, False))
                target_xform = UsdGeom.Xform.Define(target_stage, target_xform_path)
                __set_xform_prim_transform(target_xform, transforms[i])
                target_path = target_xform_path.AppendChild(source_path.name)
            else:
                target_path = root_path.AppendChild(source_path.name)
                target_path = Sdf.Path(omni.usd.get_stage_next_free_path(target_stage, target_path, False))

            all_external_references = set([])

            def on_prim_spec_path(root_path, prim_spec_path):
                if prim_spec_path.IsPropertyPath():
                    return

                if prim_spec_path == Sdf.Path.absoluteRootPath:
                    return

                prim_spec = source_layer.GetPrimAtPath(prim_spec_path)
                if not prim_spec or not prim_spec.HasInfo(Sdf.PrimSpec.ReferencesKey):
                    return

                op = prim_spec.GetInfo(Sdf.PrimSpec.ReferencesKey)
                items = []
                items = op.ApplyOperations(items)

                for item in items:
                    if not item.primPath.HasPrefix(root_path):
                        all_external_references.add(item.primPath)

            # Traverse the source prim tree to find all references that are outside of the source tree.
            source_layer.Traverse(source_path, partial(on_prim_spec_path, source_path))

            # Copy dependencies
            for path in all_external_references:
                Sdf.CreatePrimInLayer(target_layer, path)
                Sdf.CopySpec(source_layer, path, target_layer, path)

            Sdf.CreatePrimInLayer(target_layer, target_path)
            Sdf.CopySpec(source_layer, source_path, target_layer, target_path)

            target_prim = target_stage.GetPrimAtPath(target_path)
            if transforms[i]:
                __set_xform_prim_transform(target_prim, Gf.Matrix4d(1.0))

            # Edit UI info of compound
            spec = target_layer.GetPrimAtPath(target_path)
            attributes = spec.attributes

            if UsdUI.Tokens.uiDisplayGroup not in attributes:
                attr = Sdf.AttributeSpec(spec, UsdUI.Tokens.uiDisplayGroup, Sdf.ValueTypeNames.Token)
                attr.default = "Material Graphs"

            if UsdUI.Tokens.uiDisplayName not in attributes:
                attr = Sdf.AttributeSpec(spec, UsdUI.Tokens.uiDisplayName, Sdf.ValueTypeNames.Token)
                attr.default = target_path.name

            if "ui:order" not in attributes:
                attr = Sdf.AttributeSpec(spec, "ui:order", Sdf.ValueTypeNames.Int)
                attr.default = 1024

            # OM-90363: Copy variants, this need to happen recursively for all children of the current prim
            _duplicate_variant_sets(prims[i], target_prim)
            for child in _get_all_children(prims[i]):
                child_target_path = target_path.AppendPath(child.GetPath().MakeRelativePath(source_path))
                _duplicate_variant_sets(child, target_stage.GetPrimAtPath(child_target_path))
    else:
        source_path = prims[0].GetPath()
            
        target_path = root_path.AppendChild(source_path.name)

        target_path = Sdf.Path(omni.usd.get_stage_next_free_path(target_stage, target_path, False))
        target_layer.defaultPrim = source_path.name

        all_external_references = set([])

        def on_prim_spec_path(root_path, prim_spec_path):
            if prim_spec_path.IsPropertyPath():
                return

            if prim_spec_path == Sdf.Path.absoluteRootPath:
                return

            prim_spec = source_layer.GetPrimAtPath(prim_spec_path)
            if not prim_spec or not prim_spec.HasInfo(Sdf.PrimSpec.ReferencesKey):
                return

            op = prim_spec.GetInfo(Sdf.PrimSpec.ReferencesKey)
            items = []
            items = op.ApplyOperations(items)

            for item in items:
                if not item.primPath.HasPrefix(root_path):
                    all_external_references.add(item.primPath)

        # Traverse the source prim tree to find all references that are outside of the source tree.
        source_layer.Traverse(source_path, partial(on_prim_spec_path, source_path))

        # Copy dependencies
        for path in all_external_references:
            Sdf.CreatePrimInLayer(target_layer, path)
            Sdf.CopySpec(source_layer, path, target_layer, path)

        Sdf.CreatePrimInLayer(target_layer, target_path)
        Sdf.CopySpec(source_layer, source_path, target_layer, target_path)

        target_prim = target_stage.GetPrimAtPath(target_path)

        # Edit UI info of compound
        spec = target_layer.GetPrimAtPath(target_path)
        attributes = spec.attributes

        if UsdUI.Tokens.uiDisplayGroup not in attributes:
            attr = Sdf.AttributeSpec(spec, UsdUI.Tokens.uiDisplayGroup, Sdf.ValueTypeNames.Token)
            attr.default = "Material Graphs"

        if UsdUI.Tokens.uiDisplayName not in attributes:
            attr = Sdf.AttributeSpec(spec, UsdUI.Tokens.uiDisplayName, Sdf.ValueTypeNames.Token)
            attr.default = target_path.name

        if "ui:order" not in attributes:
            attr = Sdf.AttributeSpec(spec, "ui:order", Sdf.ValueTypeNames.Int)
            attr.default = 1024

        # OM-90363: Copy variants, this need to happen recursively for all children of the current prim
        _duplicate_variant_sets(prims[i], target_prim)
        for child in _get_all_children(prims[i]):
            child_target_path = target_path.AppendPath(child.GetPath().MakeRelativePath(source_path))
            _duplicate_variant_sets(child, target_stage.GetPrimAtPath(child_target_path))

    # Save
    target_layer.Save()

    # OM-61553: Add exported USD file to recent files
    # since the layer save will not trigger stage save event, it can't be caught automatically
    # by omni.kit.menu.file.scripts stage event sub, thus we have to manually put it in the
    # carb settings to trigger the update
    _add_to_recent_files(path)


def _add_to_recent_files(filename: str):
    """Utility to add the filename to recent file list."""
    if not filename:
        return

    # OM-87021: The "recentFiles" setting is deprecated. However, the welcome extension still
    # reads from it so we leave this code here for the time being.
    import carb.settings
    recent_files = carb.settings.get_settings().get("/persistent/app/file/recentFiles") or []
    recent_files.insert(0, filename)
    carb.settings.get_settings().set("/persistent/app/file/recentFiles", recent_files)

    # Emit a file saved event to the event stream
    message_bus = omni.kit.app.get_app().get_message_bus_event_stream()
    message_bus.push(FILE_SAVED_EVENT, payload=FileEventModel(url=filename).dict())


class ExportPrimUSDLegacy:
    """
    It's still used in Material Graph
    """

    EXPORT_USD_EXTS = ("usd", "usda", "usdc")

    def __init__(self, select_msg="Save As", save_msg="Save", save_dir=None, postfix_name=None):
        self._prim = None
        self._dialog = None
        self._select_msg = select_msg
        self._save_msg = save_msg
        self._save_dir = save_dir
        self._postfix_name = postfix_name
        self._last_dir = None

    def destroy(self):
        self._prim = None
        if self._dialog:
            self._dialog.destroy()
            self._dialog = None

    def export(self, prim):
        self.destroy()

        if isinstance(prim, list):
            self._prim = prim
        else:
            self._prim = [prim]

        write_dir = self._save_dir
        if not write_dir:
            write_dir = last_dir if last_dir else ""

        try:
            from omni.kit.window.filepicker import FilePickerDialog

            usd_filter_descriptions = [f"{ext.upper()} (*.{ext})" for ext in self.EXPORT_USD_EXTS]
            usd_filter_descriptions.append("All Files (*)")
            self._dialog = FilePickerDialog(
                self._select_msg,
                apply_button_label=self._save_msg,
                current_directory=write_dir,
                click_apply_handler=self.__on_apply_save,
                item_filter_options=usd_filter_descriptions,
                item_filter_fn=self.__on_filter_item,
            )
        except:
            carb.log_info(f"Failed to import omni.kit.window.filepicker")

    def __on_filter_item(self, item: "FileBrowserItem") -> bool:
        if not item or item.is_folder:
            return True
        if self._dialog.current_filter_option < len(self.EXPORT_USD_EXTS):
            # Show only files with listed extensions
            return item.path.endswith("." + self.EXPORT_USD_EXTS[self._dialog.current_filter_option])
        else:
            # Show All Files (*)
            return True

    def __on_apply_save(self, filename: str, dir: str):
        """Called when the user presses the Save button in the dialog"""
        # Get the file extension from the filter
        if not filename.lower().endswith(self.EXPORT_USD_EXTS):
            if self._dialog.current_filter_option < len(self.EXPORT_USD_EXTS):
                filename += "." + self.EXPORT_USD_EXTS[self._dialog.current_filter_option]
        # Add postfix name
        if self._postfix_name:
            filename = filename.replace(".usd", f".{self._postfix_name}.usd")

        # TODO: Nucleus
        path = omni.client.combine_urls(dir, filename)
        self._dialog.hide()

        export(f"{path}", self._prim)

        self._prim = None

        global last_dir
        last_dir = dir


class ExportPrimUSD:
    """Utility class for exporting USD prims."""

    def __init__(self, select_msg="Save As", save_msg="Save", save_dir=None, postfix_name=None):
        """
        Instantiates an instance of this utility class.

        Keyword Args:
            select_msg (str): Title for file exporter dialog, default to "Save As"
            save_msg (str): Deprecated, used for legacy usd prim export.
            save_dir (Optional[str]): Deprecated, used for legacy usd prim export.
            postfix_name (Optional[str]): Deprecated, used for legacy usd prim export.
        """
        self._select_msg = select_msg

        if save_msg != "Save" or save_dir or postfix_name:
            self._legacy = ExportPrimUSDLegacy(select_msg, save_msg, save_dir, postfix_name)
        else:
            self._legacy = None

    def destroy(self):
        """Destroys the instance."""
        if self._legacy:
            self._legacy.destroy()

    def export(self, prims: List[Usd.Prim]):
        """
        Main function for exporting prims. Displays a file exporter dialog for user interaction.

        Args:
            prims (List[Usd.Prim]): Prims to be exported.
        """
        if self._legacy:
            return self._legacy.export(prims)

        file_exporter = get_file_exporter()
        if file_exporter:
            # OM-48055: Use the current stage directory as default save directory if export selected happened for the
            #  first time after opened the current stage; Otherwise use the last saved directory that user specifed.
            global _default_save_dir
            filename = prims[0].GetName() if prims else ""
            dirname = _default_save_dir if _default_save_dir else ""
            filename_url = ""
            if dirname:
                filename_url = dirname.rstrip('/') + '/'
            if filename:
                filename_url += filename

            file_exporter.show_window(
                title=self._select_msg,
                export_button_label="Save Selected",
                export_handler=partial(self.__on_apply_save, prims),
                # OM-61553: Add default filename for export using the selected prim name
                filename_url=filename_url or None,
            )

    def __on_apply_save(
        self, prims: List[Usd.Prim], filename: str, dirname: str, extension: str, selections: List[str] = []
    ):
        """Called when the user presses the Save button in the dialog"""
        if prims:
            path = omni.client.combine_urls(dirname, f"{filename}{extension}")
            export(path, prims)
            # update default save dir after successful export
            global _default_save_dir
            _default_save_dir = dirname
