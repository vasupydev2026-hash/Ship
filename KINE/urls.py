from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),

    # Cart pages first
    path('cart/', include(('cartPage.urls', 'cartPage'), namespace='cartPage')),

    # Landing & base pages
    path('', include('landing.urls')),
    path('base/', include('base.urls')),

    path('app/', include('app.urls')),
    path('wishlist/', include('wishlist.urls')),
    path('address/', include(('address.urls', 'address'), namespace='address')),
    path('profile/', include('profile.urls')),
    path('orders/', include('orders.urls')),
    path('', include('faqpage.urls')),
    path('', include('aboutus.urls')),
    path('', include('terms_co.urls')),
    path('', include('emailapp.urls')),

]
