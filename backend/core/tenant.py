class SchoolScopedQuerysetMixin:
    """Scopes a private school queryset from the authenticated admin profile."""

    school_lookup = "school"

    def get_school(self):
        return self.request.user.school_administrator.school

    def get_queryset(self):
        queryset = super().get_queryset()
        return queryset.filter(**{self.school_lookup: self.get_school()})

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["school"] = self.get_school()
        return context


class ParentScopedQuerysetMixin:
    """Scopes parent-visible rows through ParentStudent ownership links."""

    parent_lookup = "parent_links__parent"

    def get_parent(self):
        return self.request.user.parent_profile

    def get_queryset(self):
        queryset = super().get_queryset()
        return queryset.filter(**{self.parent_lookup: self.get_parent()}).distinct()

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["parent"] = self.get_parent()
        return context
