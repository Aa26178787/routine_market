from django import template

register = template.Library()


@register.filter
def won(value):
    try:
        return f"₩{int(value):,}"
    except (ValueError, TypeError):
        return "—"
