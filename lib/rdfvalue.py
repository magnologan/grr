#!/usr/bin/env python
# Copyright 2012 Google Inc.
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""AFF4 RDFValue implementations.

This module contains all RDFValue implementations.

NOTE: This module uses the class registry to contain all implementations of
RDFValue class, regardless of where they are defined. To do this reliably, these
implementations must be imported _before_ the relevant classes are referenced
from this module.
"""


import abc
import calendar
import datetime
import functools
import posixpath
import time
import urlparse

import dateutil
from dateutil import parser

from google.protobuf import descriptor
from google.protobuf import text_format

from grr.lib import registry
from grr.lib import utils
from grr.proto import jobs_pb2


# Factor to convert from seconds to microseconds
MICROSECONDS = 1000000


class RDFValue(object):
  """Baseclass for values.

  RDFValues are serialized to and from the data store.
  """
  __metaclass__ = registry.MetaclassRegistry

  # This is how the attribute will be serialized to the data store. It must
  # indicate both the type emitted by SerializeToDataStore() and expected by
  # ParseFromDataStore()
  data_store_type = "bytes"

  def __init__(self, initializer=None, age=None):
    """Constructor must be able to take no args.

    Args:
      initializer: Optional parameter to construct from.
      age: The age of this entry as an RDFDatetime. If not provided, create a
           new instance.
    """
    # Default timestamp is now.
    if age is None:
      age = RDFDatetime(age=0)

    self._age = age

    # Allow an RDFValue to be initialized from an identical RDFValue.
    if initializer.__class__ == self.__class__:
      self.ParseFromString(initializer.SerializeToString())

    elif initializer is not None:
      self.ParseFromString(initializer)

  def Copy(self):
    """Make a new copy of this RDFValue."""
    return self.__class__(initializer=self.SerializeToString())

  @property
  def age(self):
    return RDFDatetime(self._age, age=0)

  @age.setter
  def age(self, value):
    """When assigning to this attribute it must be an RDFDatetime."""
    self._age = RDFDatetime(value, age=0)

  def ParseFromDataStore(self, data_store_obj):
    """Serialize from an object read from the datastore."""
    return self.ParseFromString(data_store_obj)

  @abc.abstractmethod
  def ParseFromString(self, string):
    """Given a string, parse ourselves from it."""
    pass

  def SerializeToDataStore(self):
    """Serialize to a datastore compatible form."""
    return self.SerializeToString()

  @abc.abstractmethod
  def SerializeToString(self):
    """Serialize into a string which can be parsed using ParseFromString."""

  def AsProto(self):
    """Serialize into an RDFValue protobuf."""
    return jobs_pb2.RDFValue(age=int(self.age),
                             name=self.__class__.__name__,
                             data=self.SerializeToString())

  def __iter__(self):
    """This allows every RDFValue to be iterated over."""
    yield self

  def __hash__(self):
    return hash(self.SerializeToString())

  def Summary(self):
    """Return a summary representation of the object."""
    return str(self)

  @classmethod
  def Fields(cls, name):
    """Return a list of fields which can be queried from this value."""
    return [name]

  @staticmethod
  def ContainsMatch(attribute, filter_implemention, regex):
    return filter_implemention.PredicateContainsFilter(attribute, regex)

  # The operators this type supports in the query language
  operators = dict(contains=(1, "ContainsMatch"))

# This will register all classes into this modules's namespace regardless of
# where they are defined. This allows us to decouple the place of definition of
# a class (which might be in a plugin) from its use which will reference this
# module.
RDFValue.classes = globals()


class RDFBytes(RDFValue):
  """An attribute which holds bytes."""
  data_store_type = "bytes"

  _value = ""

  def ParseFromString(self, string):
    self._value = string

  def SerializeToString(self):
    return self._value

  def __str__(self):
    return utils.SmartStr(self._value)

  def __eq__(self, other):
    return self._value == other

  def __ne__(self, other):
    return self._value != other

  def __hash__(self):
    return hash(self._value)

  def __bool__(self):
    return bool(self._value)

  def __nonzero__(self):
    return bool(self._value)


class RDFString(RDFBytes):
  """Represent a simple string."""

  data_store_type = "string"

  _value = u""

  @staticmethod
  def Startswith(attribute, filter_implemention, string):
    return filter_implemention.PredicateContainsFilter(
        attribute, "^" + utils.EscapeRegex(string))

  operators = RDFValue.operators.copy()
  operators["matches"] = (1, "ContainsMatch")
  operators["="] = (1, "ContainsMatch")
  operators["startswith"] = (1, "Startswith")

  def __unicode__(self):
    return utils.SmartUnicode(self._value)

  def SerializeToString(self):
    return utils.SmartStr(self._value)

  def SerializeToDataStore(self):
    return utils.SmartUnicode(self._value)


class RDFSHAValue(RDFBytes):
  """SHA256 hash."""

  data_store_type = "bytes"

  def __str__(self):
    return self._value.encode("hex")


@functools.total_ordering
class RDFInteger(RDFString):
  """Represent an integer."""

  data_store_type = "integer"

  def __init__(self, initializer=None, age=None):
    super(RDFInteger, self).__init__(initializer=initializer, age=age)
    if initializer is None:
      self._value = 0

  def ParseFromString(self, string):
    self._value = 0
    if string:
      self._value = int(string)

  def SerializeToDataStore(self):
    """Use varint to store the integer."""
    return int(self._value)

  def Set(self, value):
    if isinstance(value, (long, int)):
      self._value = value
    else:
      self.ParseFromString(value)

  def __long__(self):
    return long(self._value)

  def __int__(self):
    return int(self._value)

  def __eq__(self, other):
    return self._value == other

  def __lt__(self, other):
    return self._value < other

  def __and__(self, other):
    return self._value & other

  def __or__(self, other):
    return self._value | other

  def __add__(self, other):
    return self._value + other

  def __radd__(self, other):
    return self._value + other

  def __iadd__(self, other):
    self._value += other
    return self

  def __sub__(self, other):
    return self._value - other

  def __rsub__(self, other):
    return other - self._value

  def __isub__(self, other):
    self._value -= other
    return self

  def __mul__(self, other):
    return self._value * other

  def __div__(self, other):
    return self._value / other

  @staticmethod
  def LessThan(attribute, filter_implemention, value):
    return filter_implemention.PredicateLessThanFilter(attribute, long(value))

  @staticmethod
  def GreaterThan(attribute, filter_implemention, value):
    return filter_implemention.PredicateGreaterThanFilter(
        attribute, long(value))

  @staticmethod
  def Equal(attribute, filter_implemention, value):
    return filter_implemention.PredicateNumericEqualFilter(
        attribute, long(value))

  operators = {"<": (1, "LessThan"),
               ">": (1, "GreaterThan"),
               "=": (1, "Equal")}


class RDFDatetime(RDFInteger):
  """A date and time internally stored in MICROSECONDS."""
  converter = MICROSECONDS

  def __init__(self, initializer=None, age=None):
    super(RDFDatetime, self).__init__(None, age)
    if isinstance(initializer, RDFDatetime):
      self._value = initializer._value  # pylint: disable=protected-access

    elif isinstance(initializer, (int, long, float)):
      self._value = int(initializer)

    elif isinstance(initializer, basestring):
      try:
        # Can be just a serialized integer.
        self._value = int(initializer)
      except ValueError:
        # Try to parse from human readable string.
        self._value = self.ParseFromHumanReadable(initializer)

    elif initializer is None:
      self.Now()

    else:
      raise RuntimeError("Unknown initializer for RDFDateTime: %s." %
                         type(initializer))

  def Now(self):
    self._value = int(time.time() * self.converter)
    return self

  def __str__(self):
    """Return the date in human readable (UTC)."""
    value = self._value / self.converter
    return time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(value))

  def __unicode__(self):
    return utils.SmartUnicode(str(self))

  def AsDatetime(self):
    """Return the time as a python datetime object."""
    return datetime.datetime.utcfromtimestamp(self._value / self.converter)

  def AsSecondsFromEpoch(self):
    return self._value / self.converter

  @classmethod
  def ParseFromHumanReadable(cls, string, eoy=False):
    """Parse a human readable string of a timestamp (in local time).

    Args:
      string: The string to parse.
      eoy: If True, sets the default value to the end of the year.
           Usually this method returns a timestamp where each field that is
           not present in the given string is filled with values from the date
           January 1st of the current year, midnight. Sometimes it makes more
           sense to compare against the end of a period so if eoy is set, the
           default values are copied from the 31st of December of the current
           year, 23:59h.

    Returns:
      The parsed timestamp.
    """
    # By default assume the time is given in UTC.
    if eoy:
      default = datetime.datetime(time.gmtime().tm_year, 12, 31, 23, 59,
                                  tzinfo=dateutil.tz.tzutc())
    else:
      default = datetime.datetime(time.gmtime().tm_year, 1, 1, 0, 0,
                                  tzinfo=dateutil.tz.tzutc())

    timestamp = parser.parse(string, default=default)
    return calendar.timegm(timestamp.utctimetuple()) * cls.converter

  @classmethod
  def LessThanEq(cls, attribute, filter_implemention, value):
    return filter_implemention.PredicateLesserEqualFilter(
        attribute, cls.ParseFromHumanReadable(value, eoy=True))

  @classmethod
  def LessThan(cls, attribute, filter_implemention, value):
    """For dates we want to recognize a variety of values."""
    return filter_implemention.PredicateLesserEqualFilter(
        attribute, cls.ParseFromHumanReadable(value))

  @classmethod
  def GreaterThanEq(cls, attribute, filter_implemention, value):
    return filter_implemention.PredicateGreaterEqualFilter(
        attribute, cls.ParseFromHumanReadable(value))

  @classmethod
  def GreaterThan(cls, attribute, filter_implemention, value):
    return filter_implemention.PredicateGreaterEqualFilter(
        attribute, cls.ParseFromHumanReadable(value, eoy=True))

  operators = {"<": (1, "LessThan"),
               ">": (1, "GreaterThan"),
               "<=": (1, "LessThanEq"),
               ">=": (1, "GreaterThanEq")}


class RDFDatetimeSeconds(RDFDatetime):
  """A DateTime class which is stored in whole seconds."""
  converter = 1


class RepeatedFieldHelper(object):
  """A helper for the RDFProto to handle repeated fields.

  This helper is intended to only be constructed from the RDFProto class.
  """

  def __init__(self, proto_list, converter):
    """Constructor.

    Args:
      proto_list: The list within the protobuf which we wrap.
      converter: An RDFProto class, or a converter function which will be
        used to coerce valued into the list.
    """
    self.proto_list = proto_list
    self.converter = converter

  def Append(self, rdf_value=None, **kwargs):
    """Append the value to our internal list."""
    # Coerce the value to the required type.
    try:
      rdf_value = self.converter(rdf_value, **kwargs)
    except (TypeError, ValueError):
      raise ValueError("Assignment value must be %s, but %s can not "
                       "be coerced." % (self.converter, type(rdf_value)))

    if issubclass(self.converter, RDFProto):
      self.proto_list.add().MergeFrom(rdf_value.ToProto())
    else:
      self.proto_list.append(rdf_value)

    return rdf_value

  def Remove(self, item):
    return self.proto_list.remove(item)

  append = utils.Proxy("Append")
  remove = utils.Proxy("Remove")

  def __getitem__(self, item):
    return self.converter(self.proto_list[item])

  def __len__(self):
    return len(self.proto_list)

  def __eq__(self, other):
    for x, y in zip(self, other):
      if x != y:
        return False

    return True


class Enum(int):
  """A class that wraps enums."""

  def __new__(cls, val, name=None):
    instance = super(Enum, cls).__new__(cls, val)
    instance.name = name or str(val)

    return instance

  def __str__(self):
    return self.name

  def __unicode__(self):
    return unicode(self.name)


class RDFProto(RDFValue):
  """A baseclass for using a protobuff as a RDFValue."""
  # This should be overriden with a suitable protobuf class
  _proto = jobs_pb2.EmptyMessage

  # This will carry the instantiated protobuf.
  _data = None

  # This is a map between protobuf fields and RDFValue objects.
  rdf_map = {}

  data_store_type = "bytes"

  # When assigning to the protobuf we need to coerce the value using these
  # converters.
  CONVERTERS = {
      descriptor.FieldDescriptor.TYPE_DOUBLE: float,
      descriptor.FieldDescriptor.TYPE_FLOAT: float,
      descriptor.FieldDescriptor.TYPE_INT64: int,
      descriptor.FieldDescriptor.TYPE_UINT64: int,
      descriptor.FieldDescriptor.TYPE_INT32: int,
      descriptor.FieldDescriptor.TYPE_FIXED64: int,
      descriptor.FieldDescriptor.TYPE_FIXED32: int,
      descriptor.FieldDescriptor.TYPE_BOOL: int,
      descriptor.FieldDescriptor.TYPE_STRING: unicode,

      # This is handled especially.
      descriptor.FieldDescriptor.TYPE_MESSAGE: None,

      descriptor.FieldDescriptor.TYPE_BYTES: str,
      descriptor.FieldDescriptor.TYPE_UINT32: int,
      descriptor.FieldDescriptor.TYPE_ENUM: int,
      descriptor.FieldDescriptor.TYPE_SFIXED32: int,
      descriptor.FieldDescriptor.TYPE_SFIXED64: int,
      descriptor.FieldDescriptor.TYPE_SINT32: int,
      descriptor.FieldDescriptor.TYPE_SINT64: int,
      }

  def __init__(self, initializer=None, age=None, **kwargs):
    super(RDFProto, self).__init__(initializer=None, age=age)
    self._data = self._proto()

    # We can be initialized from another RDFProto instance the same as us.
    if self.__class__ == initializer.__class__:
      self._data = initializer._data  # pylint: disable=protected-access
      self.age = initializer.age

    # Allow ourselves to be instantiated from a protobuf
    elif isinstance(initializer, self._proto):
      self._data = initializer

    # Initialize from a serialized protobuf.
    elif isinstance(initializer, str):
      self.ParseFromString(initializer)

    elif initializer is not None:
      raise ValueError("%s can not be initialized from %s" % (
          self.__class__.__name__, type(initializer)))

    # Update the protobuf fields from the keywords.
    for k, v in kwargs.items():
      if hasattr(self._data, k):
        setattr(self, k, v)
      else:
        raise ValueError("Keyword arg %s not known." % k)

  @classmethod
  def FromSerializedProtobuf(cls, serialized_proto):
    """Alternate constructor from a serialized protobuf."""
    x = cls()
    x.ParseFromString(serialized_proto)
    return x

  @classmethod
  def FromTextProtobuf(cls, text_proto):
    """Alternate constructor from a text dump."""
    result = cls()
    result.ParseFromTextDump(text_proto)
    return result

  def ParseFromTextDump(self, dump):
    """Parse from the text dump of the protobuf."""
    text_format.Merge(dump, self._data)

  def ParseFromString(self, string):
    self._data.ParseFromString(utils.SmartStr(string))

    return self._data

  def SerializeToString(self):
    return self._data.SerializeToString()

  def ListFields(self):
    """Return all fields in this protobuf.

    Yields:
      tuples of (name, RDFValue)
    """
    for desc, _ in self._data.ListFields():
      name = desc.name
      yield name, getattr(self, name)

  def GetFields(self, field_names):
    value = self
    for field_name in field_names:
      value = getattr(value, field_name)

    if not isinstance(value, RDFValue):
      value = RDFString(value)

    return [value]

  def __str__(self):
    return self._data.__str__()

  def __unicode__(self):
    return self._data.__unicode__()

  def __dir__(self):
    """Add the virtualized fields to the console's tab completion."""
    return (dir(super(RDFProto, self)) +
            [x.name for x in self._proto.DESCRIPTOR.fields])

  @classmethod
  def Fields(cls, name):
    return ["%s.%s" % (name, x.name) for x in cls._proto.DESCRIPTOR.fields]

  @classmethod
  def Enum(cls, value_name):
    """Make protobuf enums available through the wrapping RDFProto class."""
    return cls._proto.DESCRIPTOR.enum_values_by_name[value_name].number

  def __getattr__(self, attr):
    # Handle repeated fields especially by wrapping them in a helper.
    field_descriptor = self._proto.DESCRIPTOR.fields_by_name
    if attr in field_descriptor:
      field_descriptor = field_descriptor[attr]

      if field_descriptor.label == field_descriptor.LABEL_REPEATED:
        converter = (self.rdf_map.get(attr) or
                     self.CONVERTERS[field_descriptor.type])

        return RepeatedFieldHelper(getattr(self._data, attr), converter)

      if attr in self.rdf_map:
        return self.rdf_map[attr](getattr(self._data, attr))

      # Wrap Enums using the Enum class.
      if field_descriptor.type == field_descriptor.TYPE_ENUM:
        # Resolve the name of the Enum.
        value = getattr(self._data, attr)
        value_desc = field_descriptor.enum_type.values_by_number.get(value)
        # Enum is not really defined here. This should not happen.
        if value_desc is None:
          return value

        return Enum(getattr(self._data, attr), value_desc.name)

    # Delegate to the protobuf if possible, but do not proxy private methods.
    if not attr.startswith("_"):
      return getattr(self._data, attr)

    raise AttributeError(attr)

  def __setattr__(self, attr, value):
    """If this attr does not belong to ourselves set in the proxied protobuf.

    Args:
      attr: The attribute to set.
      value: The value to set.

    Raises:
      AttributeError: If the attribute is missing.
      ValueError: If the value is not of the correct type.
    """
    # This is a regular field in the proxied protobuf.
    if hasattr(self._data, attr) and not hasattr(self.__class__, attr):
      # Assigning None means to clear the protobuf field.
      if value is None:
        self._data.ClearField(attr)

      else:
        field_descriptor = self.DESCRIPTOR.fields_by_name[attr]

        # This is a repeated protobuf we need to assign it especially.
        if field_descriptor.label == field_descriptor.LABEL_REPEATED:
          self._data.ClearField(attr)
          helper = getattr(self, attr)

          for item in value:
            helper.Append(item)

        # This is a nested protobuf - we can not just assign it.
        elif field_descriptor.type == descriptor.FieldDescriptor.TYPE_MESSAGE:

          # Convert the target to a protobuf so we can merge it.
          try:
            nested_protobuf = getattr(self._data, attr)
            if isinstance(value, RDFProto):
              value = value.ToProto()

            nested_protobuf.CopyFrom(value)
          except (AttributeError, TypeError):
            raise ValueError("Assignment value must be of type %s" %
                             getattr(self, attr).__class__.__name__)

        else:
          converter = self.CONVERTERS[field_descriptor.type]

          # Coerce the value to the required type.
          try:
            value = converter(value)
          except (TypeError, ValueError):
            raise ValueError("Assignment value must be %s, but %s "
                             "can not be coerced." % (converter, type(value)))

          # Now assign it.
          setattr(self._data, attr, value)

    # Normal attributes are treated as usual - assign to the RDFProto object.
    else:
      object.__setattr__(self, attr, value)

  def ToProto(self):
    return self._data

  def __eq__(self, other):
    """Implement equality operator."""
    return (isinstance(other, self.__class__) and
            self.SerializeToString() == other.SerializeToString())

  def __ne__(self, other):
    return not self == other


@functools.total_ordering
class RDFURN(RDFValue):
  """An object to abstract URL manipulation."""

  data_store_type = "string"

  def __init__(self, initializer=None, age=None):
    """Constructor.

    Args:
      initializer: A string or another RDFURN.
      age: The age of this entry.
    """
    if type(initializer) == RDFURN:
      # Make a direct copy of the other object
      # pylint: disable=protected-access
      self._urn = initializer._urn
      self._string_urn = initializer._string_urn
      # pylint: enable=protected-access
      super(RDFURN, self).__init__(None, age)
      return

    super(RDFURN, self).__init__(initializer=initializer, age=age)

  def ParseFromString(self, initializer=None):
    self._urn = urlparse.urlparse(initializer, scheme="aff4")
    # Normalize the URN path component
    # namedtuple _replace() is not really private.
    # pylint: disable=W0212
    self._urn = self._urn._replace(path=utils.NormalizePath(self._urn.path))
    if not self._urn.scheme:
      self._urn = self._urn._replace(scheme="aff4")

    self._string_urn = self._urn.geturl()

  def SerializeToString(self):
    return str(self)

  def Dirname(self):
    return posixpath.dirname(self.SerializeToString())

  def Basename(self):
    return posixpath.basename(self.Path())

  def Add(self, urn, age=None):
    """Add a relative stem to the current value and return a new RDFURN.

    If urn is a fully qualified URN, replace the current value with it.

    Args:
      urn: A string containing a relative or absolute URN.
      age: The age of the object. If None set to current time.

    Returns:
       A new RDFURN that can be chained.
    """
    if isinstance(urn, RDFURN):
      return urn

    parsed = urlparse.urlparse(urn)
    if parsed.scheme != "aff4":
      # Relative name - just append to us.
      result = self.Copy(age)
      result.Update(path=utils.JoinPath(self._urn.path, urn))
    else:
      # Make a copy of the arg
      result = RDFURN(urn, age)

    return result

  def Update(self, url=None, **kwargs):
    """Update one of the fields.

    Args:
       url: An optional string containing a URL.
       **kwargs: Can be one of "schema", "netloc", "query", "fragment"
    """
    if url: self.ParseFromString(url)

    self._urn = self._urn._replace(**kwargs)  # pylint: disable=W0212
    self._string_urn = self._urn.geturl()

  def Copy(self, age=None):
    """Make a copy of ourselves."""
    if age is None:
      age = int(time.time() * MICROSECONDS)
    return RDFURN(str(self), age=age)

  def __str__(self):
    return utils.SmartStr(self._string_urn)

  def __unicode__(self):
    return utils.SmartUnicode(self._string_urn)

  def __eq__(self, other):
    return self._string_urn == other

  def __ne__(self, other):
    return self._string_urn != other

  def __lt__(self, other):
    return self._string_urn < other

  def Path(self):
    """Return the path of the urn."""
    return self._urn.path

  @property
  def scheme(self):
    return self._urn.scheme

  def Split(self, count=None):
    """Returns all the path components.

    Args:
      count: If count is specified, the output will be exactly this many path
        components, possibly extended with the empty string. This is useful for
        tuple assignments without worrying about ValueErrors:

           namespace, path = urn.Split(2)

    Returns:
      A list of path components of this URN.
    """
    if count:
      result = filter(None, self.Path().split("/", count))
      while len(result) < count:
        result.append("")

      return result

    else:
      return filter(None, self.Path().split("/"))

  def RelativeName(self, volume):
    """Given a volume URN return the relative URN as a unicode string.

    We remove the volume prefix from our own.
    Args:
      volume: An RDFURN or fully qualified url string.

    Returns:
      A string of the url relative from the volume or None if our URN does not
      start with the volume prefix.
    """
    string_url = utils.SmartUnicode(self)
    volume_url = utils.SmartUnicode(volume)
    if string_url.startswith(volume_url):
      result = string_url[len(volume_url):]
      # Must always return a relative path
      while result.startswith("/"): result = result[1:]

      # Should return a unicode string.
      return utils.SmartUnicode(result)

    return None

  def __hash__(self):
    return hash(self._string_urn)

  def __repr__(self):
    return "<RDFURN@%X = %s age=%s>" % (hash(self), str(self), self.age)


class Subject(RDFURN):
  """A psuedo attribute representing the subject of an AFF4 object."""

  @staticmethod
  def ContainsMatch(unused_attribute, filter_implemention, regex):
    return filter_implemention.SubjectContainsFilter(regex)

  @staticmethod
  def Startswith(unused_attribute, filter_implemention, string):
    return filter_implemention.SubjectContainsFilter(
        "^" + utils.EscapeRegex(string))

  @staticmethod
  def HasAttribute(unused_attribute, filter_implemention, string):
    return filter_implemention.HasPredicateFilter(string)

  operators = dict(matches=(1, "ContainsMatch"),
                   contains=(1, "ContainsMatch"),
                   startswith=(1, "Startswith"),
                   has=(1, "HasAttribute"))