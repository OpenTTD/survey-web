module Jekyll
    module OpenTTDFilters

        def percentage(value)
            return sprintf("%.1f", value * 100)
        end
    end
end

Liquid::Template.register_filter(Jekyll::OpenTTDFilters)
