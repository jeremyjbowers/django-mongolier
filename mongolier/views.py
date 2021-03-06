"""
views.py

A module that replicates django's class based views for mongodb

"""
try:
    from django.db.settings import DEFAULT_PAGINATION
except ImportError:
    DEFAULT_PAGINATION = 25

from django.views.generic.base import View
from django.http import Http404, HttpResponseRedirect
from django.template.response import TemplateResponse


class BaseMongoMixin(object):
    connection = None
    sort = None
    query = None
    results = None
    context_object_name = None
    template_name = None
    class_type = None

    def get_context_data(self, *args, **kwargs):
        context = {'object_list': self.results}
        context.update(**kwargs)
        context[self.context_object_name] = self.results
        return context

    def get_template_name(self):
        if self.template_name == None:
            return u'%s/%s_%s.html' % (self.connection.collection, self.connection.collection, self.class_type)
        else:
            return self.template_name

    def render_to_response(self, context):
        return TemplateResponse(request=self.request,
            template=self.get_template_name(),
            context=context,)


class BasePaginatedMongoMixin(BaseMongoMixin):
    pages = None
    page = None
    next_page_number = None
    previous_page_number = None
    offset = None
    pagination_limit = DEFAULT_PAGINATION
    page_range = None

    def get_context_data(self, *args, **kwargs):
        context = super(BasePaginatedMongoMixin, self).get_context_data(*args, **kwargs)
        context['page'] = self.page
        context['pages'] = self.pages
        context['page_range'] = self.page_range
        context['previous_page_number'] = self.previous_page_number
        context['next_page_number'] = self.next_page_number
        return context


class DetailView(BaseMongoMixin, View):
    class_type = 'detail'

    def get_object(self, *args, **kwargs):
        if self.query:
            kwargs.update(self.query)

        obj_query = self.connection.api.find_one(kwargs, sort=self.sort)

        if obj_query == None:
            raise Http404(u"List is empty.")
        else:
            return obj_query, 'query'

    def get(self, request, *args, **kwargs):
        """
        Overrides the built in get() function on the base View class.
        Gets the object and the context.
        Returns a redirect if there's an issue with the page number.
        """
        # If the type of response is a query:
        if self.get_object()[1] == 'query':

            # Set the results to the first part of the tuple.
            self.results = self.get_object(*args, **kwargs)[0]

            # If there are no results ...
            if not self.results:

                #... raise a 404.
                raise Http404(u"List is empty.")

            # If there are results, set the context data.
            context = self.get_context_data()

            # Return render_to_response with the context data.
            return self.render_to_response(context)

        # Otherwise, if the response is a redirect ...
        elif self.get_object()[1] == 'redirect':

            #... execute the redirect.
            return HttpResponseRedirect(self.get_object()[0])


class PagelessListView(BaseMongoMixin, View):

    class_type = 'list'
    show_id = False

    def get_list(self, *args, **kwargs):
        """
        Provides a list of JSON objects from a MongoConnection class.
        """
        if self.query:
            kwargs.update(self.query)
        # Get the total count and the number of pages.
        obj_query = self.connection.api.find(kwargs, sort=self.sort)

        query_list = []

        # Append each item to the query_list.
        for item in obj_query:
            item_dict = {}
            item_as_kwargs = dict(item)
            item_dict.update(**item_as_kwargs)
            if self.show_id:
                item_dict['id'] = str(item['_id'])
            item_dict.pop('_id')
            query_list.append(item_dict)
        # Return the query list, and set the type of return to query.
        return query_list, 'query'

    def get(self, request, *args, **kwargs):
        """
        Overrides the built in get() function on the base View class.
        Gets the object and the context.
        Returns a redirect if there's an issue with the page number.
        """

        # If the type of response is a query:
        if self.get_list()[1] == 'query':

            # Set the results to the first part of the tuple.
            self.results = self.get_list(*args, **kwargs)[0]

            # If there are no results ...
            if len(self.results) == 0:

                #... raise a 404.
                raise Http404(u"List is empty.")

            # If there are results, set the context data.
            context = self.get_context_data(**kwargs)

            # Return render_to_response with the context data.
            return self.render_to_response(context)

        # Otherwise, if the response is a redirect ...
        elif self.get_list()[1] == 'redirect':

            #... execute the redirect.
            return HttpResponseRedirect(self.get_list()[0])


class ListView(BasePaginatedMongoMixin, View):
    """
    Provides a generic list view for MongoDB.
    """
    # Set the class type.
    class_type = 'list'

    def get_list(self, *args, **kwargs):
        """
        Provides a list of JSON objects from a MongoConnection class.
        """
        if self.query:
            kwargs.update(self.query)
        # Get the total count and the number of pages.
        total_count = self.connection.api.find(kwargs, sort=self.sort).count()

        if (total_count % self.pagination_limit) > 0:
            self.pages = (total_count / self.pagination_limit) + 1
        else:
            self.pages = (total_count / self.pagination_limit)

        if self.pages == 1:
            self.page_range = [1]
        else:
            self.page_range = range(1, self.pages + 1)

        try:
            # Try to get the page from the URL.
            self.page = int(self.request.GET['page'])

        except KeyError:

            # If there's no page in the URL, set the page to 1.
            self.page = 1
            self.offset = 0

        # If we can get the page from the URL, calculate the offset.
        # First, test if the current page is 0.
        if self.page == 0:

            # If so, short circuit the process and return a redirect URL while setting the type as a redirect.
            redirect_url = '%s?page=%s' % (self.request.META['PATH_INFO'], 1)
            return redirect_url, 'redirect'

        # Next, check if the current page is less than the total number of pages.
        elif self.page <= self.pages:

            # If so, set the offset to the 1-indexed page number * the pagination limit.
            self.offset = (self.page - 1) * self.pagination_limit

            # Set the previous/next page numbers.
            if self.page == 1 and self.page == self.pages:
                pass

            elif self.page == 1:
                self.next_page_number = 2

            elif self.page == self.pages:
                self.previous_page_number = self.page - 1

            else:
                self.next_page_number = self.page + 1
                self.previous_page_number = self.page - 1

        # Finally, check if the current page is greater than the total number of pages.
        elif self.page > self.pages:

            # If so, short circuit the process and return a redirect URL while setting the type as a redirect.
            redirect_url = '%s?page=%s' % (self.request.META['PATH_INFO'], self.pages)
            return redirect_url, 'redirect'

        # Send along the connection query with the sort attached.
        obj_query = self.connection.api.find(kwargs, limit=self.pagination_limit, skip=self.offset, sort=self.sort)

        # Set up a query list.
        query_list = []

        # Append each item to the query_list.
        for item in obj_query:
            item_dict = {}
            item_as_kwargs = dict(item)
            item_dict.update(**item_as_kwargs)
            item_dict['id'] = str(item['_id'])
            item_dict.pop('_id')
            query_list.append(item_dict)

        # Return the query list, and set the type of return to query.
        return query_list, 'query'

    def get(self, request, *args, **kwargs):
        """
        Overrides the built in get() function on the base View class.
        Gets the object and the context.
        Returns a redirect if there's an issue with the page number.
        """

        # If the type of response is a query:
        if self.get_list()[1] == 'query':

            # Set the results to the first part of the tuple.
            self.results = self.get_list()[0]

            # If there are no results ...
            if len(self.results) == 0:

                #... raise a 404.
                raise Http404(u"List is empty.")

            # If there are results, set the context data.
            context = self.get_context_data(**kwargs)

            # Return render_to_response with the context data.
            return self.render_to_response(context)

        # Otherwise, if the response is a redirect ...
        elif self.get_list()[1] == 'redirect':

            #... execute the redirect.
            return HttpResponseRedirect(self.get_list()[0])
