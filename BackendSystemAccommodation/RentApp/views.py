import cloudinary.uploader
import requests
from django.contrib.auth import logout
from django.shortcuts import render
from django.template.response import TemplateResponse
from django.utils import timezone
from oauth2_provider.models import AccessToken, RefreshToken
from rest_framework import viewsets, permissions, status, generics
from rest_framework.decorators import action
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response

from .pagination import CustomPageNumberPagination
from .utils import sendEmail

from RentApp import perms
from RentApp.models import User, Accommodation, ImageAccommodation, Post, CommentPost, Follow, Notification, ImagePost, \
    CommentAccommodation
from RentApp.serializers import UserSerializer, AccommodationSerializer, \
    CommentPostSerializer, PostSerializer, FollowSerializer, NotificationSerializer, CommentAccommodationSerializer


# Create your views here.
class UserViewSet(viewsets.ViewSet, generics.ListAPIView, generics.DestroyAPIView):
    queryset = User.objects.all()
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated, ]

    def get_permissions(self):
        if self.action in ['update_user', 'destroy']:
            permission_classes = [perms.OwnerAuthenticated]
        if self.action in ['register_user', 'detail_user', 'list']:
            permission_classes = [permissions.AllowAny]
        return [permission() for permission in permission_classes]

    @action(methods=['POST'], detail=False, url_path='register')
    def register_user(self, request):
        try:
            data = request.data
            role = request.data.get('role')
            avatar = request.data.get('avatar_user')

            if role in [User.Role.ADMIN]:
                new_user = User.objects.create_user(
                    first_name=data.get('first_name'),
                    last_name=data.get('last_name'),
                    username=data.get('username'),
                    email=data.get('email'),
                    password=data.get('password'),
                    phone=data.get('phone'),
                    role=role,
                )
                return Response(data=UserSerializer(new_user, context={'request': request}).data,
                                status=status.HTTP_201_CREATED)

            if role in [User.Role.HOST, User.Role.TENANT] and not avatar:
                return Response({'error': 'Avatar user not found'}, status=status.HTTP_400_BAD_REQUEST)

            res = cloudinary.uploader.upload(data.get('avatar_user'), folder='avatar_user/')

            new_user = User.objects.create_user(
                first_name=data.get('first_name'),
                last_name=data.get('last_name'),
                username=data.get('username'),
                email=data.get('email'),
                password=data.get('password'),
                phone=data.get('phone'),
                role=role,
                avatar_user=res['secure_url'],
            )
            return Response(data=UserSerializer(new_user, context={'request': request}).data,
                            status=status.HTTP_201_CREATED)
        except Exception as e:
            print(f"Error: {str(e)}")
            return Response({'error': 'Error creating user'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(methods=['GET'], detail=False, url_path='detail')
    def detail_user(self, request):
        try:
            current_user = User.objects.get(username=request.user)
            return Response(data=UserSerializer(current_user, context={'request': request}).data, status=status.HTTP_200_OK)
        except Exception as e:
            print(f"Error: {str(e)}")
            return Response({"Error": "Server error"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(methods=['PATCH'], detail=True, url_path='update')
    def update_user(self, request, pk):
        try:
            data = request.data
            user_instance = self.get_object()

            for key, value in data.items():
                setattr(user_instance, key, value)
            if data.get('avatar_user') is None:
                pass
            else:
                avatar_file = data.get('avatar_user')
                res = cloudinary.uploader.upload(avatar_file, folder='avatar_user/')
                user_instance.avatar_user = res['secure_url']
            user_instance.save()
            return Response(data=UserSerializer(user_instance, context={'request': request}).data,
                            status=status.HTTP_200_OK)
        except Exception as e:
            print(f"Error: {str(e)}")
            return Response({"Error": "Server error"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(methods=['GET'], url_path='current_user', url_name='current_user', detail=False)
    def current_user(self, request):
        return Response(UserSerializer(request.user).data)

    @action(methods=['POST'], detail=False, url_path='follow')
    def follow(self, request):
        try:
            queries = self.queryset
            username_follow = request.query_params.get('username')
            user_follow = queries.get(username=username_follow)
            user = request.user
            follow, followed = Follow.objects.get_or_create(user=user, follow=user_follow)
            if followed:
                NotificationsViewSet.create_notification_follow(f'{user} started following {user_follow.username}', sender=user, user_receive=user_follow)
            if not followed:
                follow.delete()
                return Response(status=status.HTTP_204_NO_CONTENT)
            return Response(data=FollowSerializer(follow).data, status=status.HTTP_201_CREATED)
        except Exception as e:
            print(f"Error: {str(e)}")
            return Response({"Error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(methods=['GET'], detail=False, url_path='follower')
    def follower(self, request):
        try:
            user = request.user
            userid = User.objects.get(username=user).id
            followers = Follow.objects.filter(follow_id=userid)
            follower_array = []
            for follower in followers:
                follower_array.append(follower.user_id)
            dataUser = {
                'user': str(user),
                'followers': follower_array
            }
            return Response(dataUser, status=status.HTTP_200_OK)
        except Exception as e:
            print(f"Error: {str(e)}")
            return Response({"Error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(methods=['GET'], detail=False, url_path='following')
    def following(self, request):
        try:
            user = request.user
            userid = User.objects.get(username=user).id
            following_user = Follow.objects.filter(user_id=userid)
            following_array = []
            for follower in following_user:
                following_array.append(follower.follow_id)
            dataUser = {
                'user': str(userid),
                'following': following_array
            }
            return Response(dataUser, status=status.HTTP_200_OK)
        except Exception as e:
            print(f"Error: {str(e)}")
            return Response({"Error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class PostViewSet(viewsets.ViewSet, generics.ListAPIView, generics.RetrieveAPIView, generics.DestroyAPIView):
    queryset = Post.objects.all()
    pagination_class = CustomPageNumberPagination
    serializer_class = PostSerializer
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def get_permissions(self):
        if self.action in ['destroy',]:
            permission_classes = [perms.OwnerAuthenticated]
        if self.action in ['list', 'retrieve', 'list']:
            permission_classes = [permissions.AllowAny]
        return [permission() for permission in permission_classes]

    @action(methods=['POST'], detail=False, url_path='create')
    def create_post(self, request):
        try:
            user = request.user
            data = request.data
            post_instance = Post.objects.create(
                content=data.get('content'),
                user_post=user,
                caption=data.get('caption'),
                description=data.get('description'),
            )
            image_instance = None
            for file in request.FILES.getlist('image'):
                res = cloudinary.uploader.upload(file, folder='post_image/')
                image_url = res['secure_url']
                image_instance = ImagePost.objects.create(
                    image=image_url,
                    post=post_instance
                )
            NotificationsViewSet.create_notification_post_accommodation(f'{user} added new post', user_send=user),
            return Response(data=PostSerializer(post_instance).data, status=status.HTTP_201_CREATED)
        except Exception as e:
            print(f"Error: {str(e)}")
            return Response({"Error": "Server error"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(methods=['POST'], detail=True, url_path='comment')
    def add_comment_post(self, request, pk):
        try:
            data = request.data
            user = request.user
            post_instance = self.get_object()
            if user != post_instance.user_post:
                NotificationsViewSet.create_notification_comment_post_accommodation(post_or_accommodation=post_instance, sender=user)
            return Response(data=CommentPostSerializer(
                CommentPost.objects.create(
                    user_comment=user,
                    post=self.get_object(),
                    text=data.get('text'),
                )
            ).data, status=status.HTTP_201_CREATED)
        except Exception as e:
            print(f"Error: {str(e)}")
            return Response({"Error": "Server error"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(methods=['GET'], detail=True, url_path='get_comment')
    def get_comments(self, request, pk):
        try:
            post = self.get_object()
            comments = CommentPost.objects.filter(post_id=post.id).filter(parent_comment__isnull=True)
            return Response(data=CommentPostSerializer(comments, many=True).data, status=status.HTTP_200_OK)
        except Exception as e:
            print(f"Error: {str(e)}")
            return Response({"Error": "Server error"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(methods=['GET'], detail=False, url_path='post_user')
    def get_post_of_user(self, request):
        try:
            user = request.user
            userid = User.objects.get(username=user).id
            posts = Post.objects.filter(user_post_id=userid)
            return Response(data=PostSerializer(posts, many=True).data, status=status.HTTP_200_OK)
        except Exception as e:
            print(f"Error: {str(e)}")
            return Response({"Error": "Server error"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(methods=['GET'], detail=False, url_path='approved')
    def get_approved_posts(self, request):
        try:
            posts = self.queryset.filter(is_approved=True)
            return Response(data=PostSerializer(posts, many=True).data, status=status.HTTP_200_OK)
        except Exception as e:
            print(f"Error: {str(e)}")
            return Response({"Error": "Server error"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(methods=['GET'], detail=False, url_path='not_approved')
    def get_posts_not_approved(self, request):
        try:
            posts = self.queryset.filter(is_approved=False)
            return Response(data=PostSerializer(posts, many=True).data, status=status.HTTP_200_OK)
        except Exception as e:
            print(f"Error: {str(e)}")
            return Response({"Error": "Server error"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    @action(methods=['PUT'],detail=True,url_path="edit_approved")
    def edit_approved(self, request, pk):
        try:

            instance = self.get_object()
            instance.is_approved = True
            instance.save()

            return Response({"message": "Successfully updated"}, status=status.HTTP_200_OK)

        except Exception as e:
            print(f"Error: {str(e)}")
            return Response({"Error": "Server error"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class CommentPostViewSet(viewsets.ViewSet, generics.ListAPIView):
    queryset = CommentPost.objects.filter(parent_comment__isnull=True)
    serializer_class = CommentPostSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_permissions(self):
        if self.action in ['edit_comment', 'delete_comment']:
            permission_classes = [perms.OwnerAuthenticated]
        if self.action in ['list']:
            permission_classes = [permissions.AllowAny]
        return [permission() for permission in permission_classes]

    @action(methods=['POST'], detail=True, url_path='reply')
    def add_reply_comment(self, request, pk):
        try:
            user = request.user
            parent_comment = CommentPost.objects.get(pk=pk)
            post_instance = Post.objects.get(pk=parent_comment.post_id)
            if user != post_instance.user_post:
                NotificationsViewSet.create_notification_comment_post_accommodation(post_or_accommodation=post_instance, sender=user)
            return Response(data=CommentPostSerializer(
                CommentPost.objects.create(
                    user_comment=request.user,
                    post=post_instance,
                    text=request.data.get('text'),
                    parent_comment=parent_comment
                )
            ).data, status=status.HTTP_201_CREATED)
        except Exception as e:
            print(f"Error: {str(e)}")
            return Response({"Error": "Server error"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(methods=['PATCH', 'PUT'], detail=True, url_path='edit')
    def edit_comment(self, request, pk):
        try:
            data = request.data
            userid = User.objects.get(username=request.user).id
            comment = CommentPost.objects.get(pk=pk)
            if comment.user_comment_id == userid:
                comment.text = data.get('text')
                comment.save()
                return Response(data=CommentPostSerializer(comment).data, status=status.HTTP_200_OK)
            else:
                return Response({"Error": "You not owner"}, status=status.HTTP_403_FORBIDDEN)
        except Exception as e:
            print(f"Error: {str(e)}")
            return Response({"Error": "Server error"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(methods=['DELETE'], detail=True, url_path='delete')
    def delete_comment(self, request, pk):
        try:
            CommentPost.objects.get(pk=pk).delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        except Exception as e:
            print(f"Error: {str(e)}")
            return Response({"Error": "Server error"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class AccommodationViewSet(viewsets.ViewSet, generics.ListAPIView, generics.DestroyAPIView):
    queryset = Accommodation.objects.all().order_by('-id')
    serializer_class = AccommodationSerializer
    pagination_class = CustomPageNumberPagination
    permission_classes = [permissions.IsAuthenticated, ]
    parser_classes = [MultiPartParser, FormParser]

    def get_queryset(self):
        query = self.queryset
        filter_accommodation = []
        longitude = self.request.query_params.get("longitude")
        latitude = self.request.query_params.get("latitude")
        key = 'AhKaL22nil7f0VevfVpYLr0hEEFmMQ_YaQ3dlIfTJYOfRv3Jbdufdyj0NSF6PVqr'
        if longitude and latitude:
            for item in query:
                reponse = requests.get(
                    f"https://dev.virtualearth.net/REST/v1/Routes/Driving?o=json&wp.0={latitude},{longitude}&wp.1={item.latitude},{item.longitude}&key={key}")
                data = reponse.json()
                if data.get("resourceSets")[0].get("resources")[0].get("travelDistance") < 10:
                    filter_accommodation.append(item)
            return filter_accommodation
        return query


    @action(methods=['POST'], detail=False, url_path='create')
    def create_accommodation(self, request):
        try:
            user = request.user
            data = request.data
            if user.role in ['HOST']:
                if len(request.FILES.getlist('image')) < 3:
                    return Response({"Error": "You must upload at least THREE image"}, status=status.HTTP_400_BAD_REQUEST)
                accommodation = Accommodation.objects.create(
                    owner=user,
                    address=data.get('address'),
                    district=data.get('district'),
                    city=data.get('city'),
                    number_of_people=data.get('number_of_people'),
                    description = data.get('description'),
                    rent_cost=data.get('rent_cost'),
                    latitude=data.get('latitude'),
                    longitude=data.get('longitude'),
                )
                for file in request.FILES.getlist('image'):
                    res = cloudinary.uploader.upload(file, folder='post_image/')
                    image_url = res['secure_url']
                    ImageAccommodation.objects.create(
                        image=image_url,
                        accommodation=accommodation
                    )
                return Response(data=AccommodationSerializer(accommodation, context={'request': request}).data,
                                status=status.HTTP_201_CREATED)
            else:
                return Response({'Error': 'You must be HOST'}, status=status.HTTP_403_FORBIDDEN)
        except Exception as e:
            print(f"Error: {str(e)}")
            return Response({"Error": "Server error"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(methods=['GET'], detail=True, url_path='detail')
    def detail_accommodation(self, request, pk):
        try:
            return Response(data=AccommodationSerializer(Accommodation.objects.get(pk=pk), context={'request': request}).data, status=status.HTTP_200_OK)
        except Exception as e:
            print(f"Error: {str(e)}")
            return Response({"Error": "Server error"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(methods=['GET'], detail=False, url_path='accommodation_user')
    def get_accommodations_user(self, request):
        try:
            user = request.user
            userid = User.objects.get(username=user).id
            accommodations = Accommodation.objects.filter(owner=userid)
            return Response(data=AccommodationSerializer(accommodations, many=True).data, status=status.HTTP_200_OK)
        except Exception as e:
            print(f"Error: {str(e)}")
            return Response({"Error": "Server error"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(methods=['GET'], detail=False, url_path='verified')
    def accommodation_is_verified(self, request):
        try:
            accommodation = self.queryset.filter(is_verified=True)
            return Response(data=AccommodationSerializer(accommodation, many=True).data, status=status.HTTP_200_OK)
        except Exception as e:
            print(f"Error: {str(e)}")
            return Response({"Error": "Server error"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(methods=['GET'], detail=False, url_path='not_verified')
    def accommodation_not_verified(self, request):
        try:
            accommodation = self.queryset.filter(is_verified=False)
            return Response(data=AccommodationSerializer(accommodation, many=True).data, status=status.HTTP_200_OK)
        except Exception as e:
            print(f"Error: {str(e)}")
            return Response({"Error": "Server error"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(methods=['POST'], detail=True, url_path='comment')
    def add_comment_accommodation(self, request, pk):
        try:
            data = request.data
            user = request.user
            accommodation_instance = self.get_object()
            if user != accommodation_instance.owner:
                NotificationsViewSet.create_notification_comment_post_accommodation(post_or_accommodation=accommodation_instance, sender=user)
            return Response(data=CommentAccommodationSerializer(
                CommentAccommodation.objects.create(
                    user_comment=user,
                    accommodation=accommodation_instance,
                    text=data.get('text')
                )
            ).data, status=status.HTTP_201_CREATED)
        except Exception as e:
            print(f"Error: {str(e)}")
            return Response({"Error": "Server error"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(methods=['GET'], detail=True, url_path='get_comment')
    def get_comment_accommodation(self, request, pk):
        try:
            accommodation_id = self.get_object().id
            comment = CommentAccommodation.objects.filter(accommodation_id=accommodation_id).filter(parent_comment__isnull=True)
            return Response(data=CommentAccommodationSerializer(comment, many=True).data, status=status.HTTP_200_OK)
        except Exception as e:
            print(f"Error: {str(e)}")
            return Response({"Error": "Server error"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class CommentAccommodationViewSet(viewsets.ViewSet):
    queryset = CommentAccommodation.objects.filter(parent_comment__isnull=True)
    serializer_class = CommentAccommodationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_permissions(self):
        if self.action in ['delete_comment',]:
            permission_classes = [perms.OwnerAuthenticated]
        return [permission() for permission in permission_classes]

    @action(methods=['POST'], detail=True, url_path='reply')
    def add_reply_comment_accommodation(self, request, pk):
        try:
            user = request.user
            parent_comment = CommentAccommodation.objects.get(pk=pk)
            accommodation_instance = Accommodation.objects.get(pk=parent_comment.accommodation_id)
            if user != accommodation_instance.owner:
                NotificationsViewSet.create_notification_comment_post_accommodation(post_or_accommodation=accommodation_instance, sender=user)
            return Response(data=CommentAccommodationSerializer(
                CommentAccommodation.objects.create(
                    user_comment=request.user,
                    accommodation=accommodation_instance,
                    text=request.data.get('text'),
                    parent_comment=parent_comment,
                )
            ).data, status=status.HTTP_201_CREATED)
        except Exception as e:
            print(f"Error: {str(e)}")
            return Response({"Error": "Server error"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(methods=['DELETE'], detail=True, url_path='delete')
    def delete_comment(self, request, pk):
        try:
            CommentAccommodation.objects.get(pk=pk).delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        except Exception as e:
            print(f"Error: {str(e)}")
            return Response({"Error": "Server error"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class NotificationsViewSet(viewsets.ViewSet, generics.ListAPIView):
    queryset = Notification.objects.all()
    serializer_class = NotificationSerializer
    permission_classes = [permissions.IsAuthenticated, ]

    def get_queryset(self):
        try:
            user = self.request.user
            userid = user.id  # Assuming user is already an instance of User model
            notifications = self.queryset.filter(recipient_id=userid)
            return notifications
        except Exception as e:
            print(f"Error: {str(e)}")
            return Response({"Error": "Server error"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def create_notification_follow(notification, sender, user_receive):
        try:
            Notification.objects.create(notice=notification, sender=sender, recipient=user_receive)
            sendEmail(notification, recipients=[user_receive.email])
            return Response({"message": "Notification created successfully"}, status=status.HTTP_201_CREATED)
        except Exception as e:
            print(f"Error: {str(e)}")
            return Response({"Error": "Server error"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def create_notification_post_accommodation(notification, user_send):
        try:
            user_send = User.objects.get(username=user_send)
            user_follow_user_send = Follow.objects.filter(follow_id=user_send.id)
            recipients_array = []
            for user in user_follow_user_send:
                recipient = User.objects.get(pk=user.user_id)
                Notification.objects.create(notice=notification, sender=user_send, recipient=recipient)
                recipients_array.append(recipient.email)
            sendEmail(notification, recipients=recipients_array)
            return Response({"message": "Notification created successfully"}, status=status.HTTP_201_CREATED)
        except Exception as e:
            print(f"Error: {str(e)}")
            return Response({"Error": "Server error"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


    def create_notification_comment_post_accommodation(post_or_accommodation, sender):
        try:
            user_send = User.objects.get(username=sender)
            notification = None
            user_receive = None
            if isinstance(post_or_accommodation, Post):
                notification = f'{sender} commented your post'
                user_receive = Post.objects.get(id=post_or_accommodation.id).user_post
            elif isinstance(post_or_accommodation, Accommodation):
                notification = f'{sender} commented your post accommodation'
                user_receive = Accommodation.objects.get(id=post_or_accommodation.id).owner
            Notification.objects.create(notice=notification, sender=user_send, recipient=User.objects.get(username=user_receive))
            return Response({"message": "Notification created successfully"}, status=status.HTTP_201_CREATED)
        except Exception as e:
            print(f"Error: {str(e)}")
            return Response({"Error": "Server error"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=['get'], url_path="notification_user")
    def user_notifications(self, request):
        try:
            user = self.request.user
            userid = User.objects.get(username=user).id
            notifications = self.queryset.filter(recipient_id=userid)
            serializer = self.serializer_class(notifications, many=True)
            return Response(serializer.data)
        except Exception as e:
            print(f"Error: {str(e)}")
            return Response({"Error": "Server error"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=True, methods=['put'], url_path="mark_as_read")
    def mark_notification_read(self, request, pk):
        try:
            notification = self.get_object()
            notification.is_read = True
            notification.save()
            return Response({"message": "Notification marked as read"}, status=status.HTTP_200_OK)
        except Notification.DoesNotExist:
            return Response({"Error": "Notification not found"}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            print(f"Error: {str(e)}")
            return Response({"Error": "Server error"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


def view_chart(request):
    def by_user_month():
        month = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]
        data = []
        users = User.objects.all()
        for i in month:
            data.append(users.filter(last_login__month=i).count())

        return {
            "labels": month,
            "data": data
        }

    def by_user_quarter():
        quarter = [1, 2, 3, 4]
        data = []
        users = User.objects.all()
        for i in quarter:
            data.append(users.filter(last_login__quarter=i).count())
        return {
            "labels": quarter,
            "data": data
        }

    def by_user_year():
        users = User.objects.all()
        start_year = users.first().last_login.year
        end_year = timezone.now().year
        data = []
        years = []

        for year in range(start_year, end_year + 1):
            data.append(users.filter(last_login__year=year).count())
            years.append(year)

        return {
            "labels": years,
            "data": data
        }

    def by_post_month():
        month = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]
        data = []
        posts = Post.objects.all()
        for i in month:
            data.append(posts.filter(created_at__month=i).count())

        return {
            "labels": month,
            "data": data
        }

    def by_post_quarter():
        quarter = [1, 2, 3, 4]
        data = []
        posts = Post.objects.all()
        for i in quarter:
            data.append(posts.filter(created_at__quarter=i).count())
        return {
            "labels": quarter,
            "data": data
        }

    def by_post_year():
        posts = Post.objects.all()
        start_year = posts.first().created_at.year
        end_year = timezone.now().year
        data = []
        years = []

        for year in range(start_year, end_year + 1):
            data.append(posts.filter(created_at__year=year).count())
            years.append(year)

        return {
            "labels": years,
            "data": data
        }

    def by_accommodation_month():
        month = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]
        data = []
        accommodation = Accommodation.objects.all()
        for i in month:
            data.append(accommodation.filter(created_at__month=i).count())

        return {
            "labels": month,
            "data": data
        }

    def by_accommodation_quarter():
        quarter = [1, 2, 3, 4]
        data = []
        accommodation = Accommodation.objects.all()
        for i in quarter:
            data.append(accommodation.filter(created_at__quarter=i).count())
        return {
            "labels": quarter,
            "data": data
        }

    def by_accommodation_year():
        accommodation = Accommodation.objects.all()
        start_year = accommodation.first().created_at.year
        end_year = timezone.now().year
        data = []
        years = []

        for year in range(start_year, end_year + 1):
            data.append(accommodation.filter(created_at__year=year).count())
            years.append(year)

        return {
            "labels": years,
            "data": data
        }


    return render(request, "chart.html", {
        'by_user_month': by_user_month,
        'by_user_quarter': by_user_quarter,
        'by_user_year': by_user_year,
        'by_post_month': by_post_month,
        'by_post_quarter': by_post_quarter,
        'by_post_year': by_post_year,
        'by_accommodation_month': by_accommodation_month,
        'by_accommodation_quarter': by_accommodation_quarter,
        'by_accommodation_year': by_accommodation_year,

    })

