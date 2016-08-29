import bpy
import mathutils

from collections import OrderedDict

import random
import time
import math

from ..libs.ins_vector import Vector

# ==================== Some base classes ====================

class Template():
    """Abstract super class.
    Templates are a description of how to create some arrangement of agents"""
    def __init__(self, inputs, settings, bpyName):
        """":param input: A list of Templates or GeoTemplates generated by the
        nodes that are connected to inputs of this node"""
        self.inputs = inputs
        self.bpyName = bpyName
        self.settings = settings

        self.buildCount = 0
        self.checkCache = None

    def build(self, pos, rot, scale, tags, cm_group):
        """Called when this template is being used to modify the scene"""
        self.buildCount += 1

    def checkRecursive(self):
        """Called after build to check that the node graph is a valid one"""
        if self.checkCache is not None:
            return self.checkCache
        if not self.check():
            self.checkCache = False, self.bpyName
            return False, self.bpyName
        for inp in self.inputs:
            r = inp.checkRecursive()
            if not r[0]:
                return r
        return True, None

    def check(self):
        """Return true if the inputs and gettings are correct"""
        return True

class GeoTemplate(Template):
    """Abstract super class.
    GeoTemplates are a description of how to create some arrangement of
     geometry"""
    def build(self, parent):
        """Called when this GeoTemplate is being used to modify the scene"""
        self.buildCount += 1

# ==================== End of base classes ====================

class GeoTemplateOBJECT(GeoTemplate):
    """For placing objects into the scene"""
    def build(self, pos, rot, scale, group):
        cp = bpy.context.scene.objects[self.settings["inputObject"]].copy()
        group.objects.link(cp)
        bpy.context.scene.objects.link(cp)
        return cp

class GeoTemplateGROUP(GeoTemplate):
    """For placing groups into the scene"""
    # TODO Meshes connected to armatures get very distorted
    def build(self, pos, rot, scale, group):
        dat = bpy.data
        gp = [o for o in dat.groups[self.settings["inputGroup"]].objects]
        group_objects = [o.copy() for o in gp]

        topObj = None

        for obj in group_objects:
            if obj.parent in gp:
                obj.parent = group_objects[gp.index(obj.parent)]
            else:
                self.rotation_euler = rot
                self.scale = Vector((scale, scale, scale))
                obj.location = pos

            group.objects.link(obj)
            bpy.context.scene.objects.link(obj)
            if obj.type == 'ARMATURE':
                aName = obj.name
            if obj.type == 'MESH':
                if len(obj.modifiers) > 0:
                    for mod in obj.modifiers:
                        if mod.type == "ARMATURE":
                            modName = mod.name
                            obj.modifiers[modName].object = dat.objects[aName]

            if obj.type == 'ARMATURE':
                topObj = obj

        return topObj

class GeoTemplateSWITCH(GeoTemplate):
    """Randomly (biased by "switchAmout") pick which of the inputs to use"""
    def build(self, pos, rot, scale, group):
        if random.random() < self.settings["switchAmout"]:
            return self.inputs["Object 1"].build(pos, rot, scale, group)
        else:
            return self.inputs["Object 2"].build(pos, rot, scale, group)

class GeoTemplatePARENT(GeoTemplate):
    """Attach a piece of geo to a bone from the parent geo"""
    def build(self, pos, rot, scale, group):
        parent = self.inputs["Parent Group"].build(pos, rot, scale, group)
        child = self.inputs["Child Object"].build(pos, rot, scale, group)
        # TODO parent child to self.settings["parentTo"] from parent


class TemplateAGENT(Template):
    """Create a CrowdMaster agent"""
    def build(self, pos, rot, scale, tags, cm_group):
        groupName = cm_group.groupName + "/" + self.settings["brainType"]
        new_group = bpy.data.groups.new(groupName)
        topObj = self.inputs["Objects"].build(pos, rot, scale, new_group)
        topObj.location = pos
        topObj.rotation_euler = rot
        topObj.scale = Vector((scale, scale, scale))

        bpy.ops.scene.cm_agent_add(agentName=topObj.name,
                                    brainType=self.settings["brainType"],
                                    groupName=cm_group.groupName,
                                    geoGroupName=new_group.name)
        # TODO set tags

class TemplateSWITCH(Template):
    """Randomly (biased by "switchAmout") pick which of the inputs to use"""
    def build(self, pos, rot, scale, tags, cm_group):
        if random.random() < self.settings["switchAmout"]:
            self.inputs["Template 1"].build(pos, rot, scale, tags, cm_group)
        else:
            self.inputs["Template 2"].build(pos, rot, scale, tags, cm_group)

class TemplateOFFSET(Template):
    """Modify the postion and/or the rotation of the request made"""
    def build(self, pos, rot, scale, tags, cm_group):
        nPos = Vector()
        nRot = Vector()
        if self.settings["offset"]:
            nPos = Vector(pos)
            nRot = Vector(rot)
        if self.settings["referenceObject"] in bpy.data.objects:
            refObj = bpy.data.objects[self.settings["referenceObject"]]
            nPos += refObj.location
            nRot += Vector(refObj.rotation_euler)
        nPos += self.settings["locationOffset"]
        nRot += self.settings["rotationOffset"]
        self.inputs["Template"].build(nPos, nRot, scale, tags, cm_group)

class TemplateRANDOM(Template):
    """Randomly modify rotation and scale of the request made"""
    def build(self, pos, rot, scale, tags, cm_group):
        rotDiff = random.uniform(self.settings["minRandRot"],
                                 self.settings["maxRandRot"])
        eul = mathutils.Euler(rot, 'XYZ')
        eul.rotate_axis('Z', math.radians(rotDiff))

        scaleDiff = random.uniform(self.settings["minRandSz"],
                                   self.settings["maxRandSz"])
        newScale = scale * scaleDiff
        self.inputs["Template"].build(pos, Vector(eul), newScale, tags, cm_group)

class TemplateRANDOMPOSITIONING(Template):
    """Place randomly"""
    def build(self, pos, rot, scale, tags, cm_group):
        for a in range(self.settings["noToPlace"]):
            if self.settings["locationType"] == "radius":
                angle = random.uniform(-math.pi, math.pi)
                x = math.sin(angle)
                y = math.cos(angle)
                length = random.random() * self.settings["radius"]
                x *= length
                y *= length
                diff = Vector((x, y, 0))
                diff.rotate(mathutils.Euler(rot))
                newPos = Vector(pos) + diff
                self.inputs["Template"].build(newPos, rot, scale, tags, cm_group)

class TemplateFORMATION(Template):
    """Place in a row"""
    def build(self, pos, rot, scale, tags, cm_group):
        placePos = Vector(pos)
        diffRow = Vector((self.settings["ArrayRowMargin"], 0, 0))
        diffCol = Vector((0, self.settings["ArrayColumnMargin"], 0))
        diffRow.rotate(mathutils.Euler(rot))
        diffCol.rotate(mathutils.Euler(rot))
        diffRow *= scale
        diffCol *= scale
        number = self.settings["noToPlace"]
        rows = self.settings["ArrayRows"]
        for fullcols in range(number//rows):
            for row in range(rows):
                self.inputs["Template"].build(placePos + fullcols*diffCol +
                                              row*diffRow, rot, scale, tags, cm_group)
        for leftOver in range(number%rows):
            self.inputs["Template"].build(placePos + (number//rows)*diffCol
                                          + leftOver*diffRow, rot, scale, tags, cm_group)

class TemplateTARGET(Template):
    """Place based on the positions of vertices"""
    def build(self, pos, rot, scale, tags, cm_group):
        obj = bpy.data.objects[self.settings["targetObject"]]
        if self.settings["overwritePosition"]:
            wrld = obj.matrix_world
            targets = [wrld*v.co for v in obj.data.vertices]
            newRot = Vector(obj.rotation_euler)
            for vert in targets:
                self.inputs["Template"].build(vert, newRot, scale, tags, cm_group)
        else:
            targets = [Vector(v.co) for v in obj.data.vertices]
            for loc in targets:
                loc.rotate(mathutils.Euler(rot))
                loc *= scale
                self.inputs["Template"].build(loc + pos, rot, scale, tags, cm_group)

class TemplateSETTAG(Template):
    """Set a tag for an agent to start with"""
    def build(self, pos, rot, scale, tags, cm_group):
        tags[self.settings["tagName"]] = self.settings["tagValue"]
        self.inputs["Template"].build(pos, rot, scale, tags, cm_group)


templates = OrderedDict([
    ("ObjectInputNodeType", GeoTemplateOBJECT),
    ("GroupInputNodeType", GeoTemplateGROUP),
    ("GeoSwitchNodeType", GeoTemplateSWITCH),
    ("TemplateSwitchNodeType", TemplateSWITCH),
    ("ParentNodeType", GeoTemplatePARENT),
    ("TemplateNodeType", TemplateAGENT),
    ("OffsetNodeType", TemplateOFFSET),
    ("RandomNodeType", TemplateRANDOM),
    ("RandomPositionNodeType", TemplateRANDOMPOSITIONING),
    ("FormationPositionNodeType", TemplateFORMATION),
    ("TargetPositionNodeType", TemplateTARGET)
])
