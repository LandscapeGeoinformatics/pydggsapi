from dataclasses import dataclass
from pydantic import BaseModel, ConfigDict, model_serializer


@dataclass
class _OmitIfNone:
    pass


OmitIfNone = _OmitIfNone()


class CommonBaseModel(BaseModel):

    @model_serializer
    def model_serialize(self):
        """
        Reconstruct the mapping considering that not all fields are necessarily annotated with 'OmitIfNone'.
        Consider the alias name if one was defined by the field.
        """
        values = {}
        for key, val in self:
            is_extra = key in (self.__pydantic_extra__ or {}) and self.model_config.get("extra") == 'allow'
            if is_extra:  # already validated by definition (otherwise it wouldn't be in __pydantic_extra__)
                values[key] = val
                continue
            if key not in self.model_fields:
                continue  # can happen if a 'CommonBaseModel' is used by a derived class
            field = self.model_fields[key]
            if any(isinstance(m, _OmitIfNone) for m in field.metadata) and val is None:
                continue
            values[field.alias or key] = val
        return values

    model_config = ConfigDict(
        populate_by_name=True,
        validate_by_name=True,
        validate_by_alias=True,
    )
