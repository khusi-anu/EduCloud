from django.shortcuts import render
from django.shortcuts import get_object_or_404
from django.shortcuts import Http404
from django.shortcuts import redirect
from django.contrib import messages

from django.views.decorators.csrf import csrf_exempt

from django.http import JsonResponse

from .models import Question
from .models import Answer
from .models import QuestionVote
from .models import AnswerVote

from academics.models import Department
from academics.models import Subject
from users.models import User

import json
from educloud.decorators import login_required

import numpy as np
from bert_serving.client import BertClient


@login_required
def all_questions(request):
    questions = Question.objects.all().order_by('-timestamp')[:20]
    departments = Department.objects.all()

    header = 'All Questions'

    logged_in_user = User.objects.get(id=request.session['user_id'])
    user_questions = {
        q.id
        for q in Question.objects.filter(user_id=logged_in_user)
    }

    return render(request, 'questions/questions.html', {
        'questions': questions,
        'departments': departments,
        'header': header,
        'title': header,
        'logged_in_user': logged_in_user,
        'questions_upvoted': logged_in_user.question_upvotes(),
        'questions_downvoted': logged_in_user.question_downvotes(),
        'user_questions': user_questions
    })


def question(request, question_id):
    this_question = get_object_or_404(Question, id=question_id)
    logged_in_user = User.objects.get(id=request.session['user_id'])

    user_questions = {
        q.id
        for q in Question.objects.filter(user_id=logged_in_user)
    }
    user_answers = {
        a.id
        for a in Answer.objects.filter(user_id=logged_in_user)
    }

    if request.method == 'GET':
        user = this_question.user
        departments = Department.objects.all()

        answers = Answer.objects.filter(question_id=question_id).order_by('timestamp')
        answers_sorted = sorted(answers.all(), key=lambda a: a.votes(), reverse=True)

        return render(request, 'questions/question.html', {
            'question': this_question,
            'user': user,
            'answers': answers_sorted,
            'departments': departments,
            'logged_in_user': logged_in_user,
            'questions_upvoted': logged_in_user.question_upvotes(),
            'questions_downvoted': logged_in_user.question_downvotes(),
            'answers_upvoted': logged_in_user.answer_upvotes(),
            'answers_downvoted': logged_in_user.answer_downvotes(),
            'user_questions': user_questions,
            'user_answers': user_answers
        })
    elif request.method == 'POST':
        ans = request.POST.get('answer')

        answer = Answer()
        answer.question = this_question
        answer.user = logged_in_user
        answer.body = ans

        answer.save()

        return redirect(f'/question/{question_id}')
    else:
        raise Http404


@csrf_exempt
def question_vote(request):
    if request.method == 'POST':
        user_id = request.session.get('user_id', -1)

        data = json.loads(request.body.decode('utf-8'))

        question_id = data.get('question_id', -1)
        vote_type = data.get('vote_type', 'NA')

        try:
            ques = Question.objects.get(id=question_id)
            user = User.objects.get(id=user_id)

            try:
                QuestionVote.objects.get(user=user, question=ques)
            except QuestionVote.DoesNotExist:
                vote = QuestionVote()
                vote.question = ques
                vote.user = user
                vote.vote_type = vote_type

                vote.save()
        except Question.DoesNotExist:
            pass
        except User.DoesNotExist:
            pass

        ques = Question.objects.get(id=question_id)
        votes = ques.votes()

        return JsonResponse({'votes': votes})
    else:
        raise Http404


@csrf_exempt
def answer_vote(request):
    if request.method == 'POST':
        user_id = request.session.get('user_id', -1)

        data = json.loads(request.body.decode('utf-8'))

        answer_id = data.get('answer_id', -1)
        vote_type = data.get('vote_type', 'NA')

        try:
            ans = Answer.objects.get(id=answer_id)
            user = User.objects.get(id=user_id)

            try:
                AnswerVote.objects.get(user=user, answer=ans)
            except AnswerVote.DoesNotExist:
                vote = AnswerVote()
                vote.answer = ans
                vote.user = user
                vote.vote_type = vote_type

                vote.save()
        except Answer.DoesNotExist:
            pass
        except User.DoesNotExist:
            pass

        ans = Answer.objects.get(id=answer_id)
        votes = ans.votes()

        return JsonResponse({'votes': votes})
    else:
        raise Http404


@login_required
def ask_question(request):
    logged_in_user = User.objects.get(id=request.session['user_id'])

    if request.method == 'GET':
        subjects = Subject.objects.all()
        departments = Department.objects.all()

        return render(request, 'questions/ask-question.html', {
            'subjects': subjects,
            'departments': departments,
            'logged_in_user': logged_in_user,
        })
    elif request.method == 'POST':
        question_name = request.POST.get('questionName', None)
        question_body = request.POST.get('questionBody', None)
        subject_id = request.POST.get('subjectId', None)

        if all((question_name, question_body, subject_id)):
            try:
                ques = Question()
                ques.name = question_name
                ques.body = question_body
                ques.user = logged_in_user
                sub = Subject.objects.get(id=subject_id)
                ques.subject = sub
                ques.save()

                return redirect(f'/academics/department/{sub.department.short_form}/questions/')
            except Subject.DoesNotExist:
                pass
        else:
            return redirect('ask-question')
    else:
        raise Http404


def get_matches(questions_list, question_):
    with BertClient(ip='localhost') as bc:
        doc_vecs = bc.encode(questions_list)
        query_vec = bc.encode([question_])[0]

        # compute normalized dot product as score
        score = np.sum(query_vec * doc_vecs, axis=1) / np.linalg.norm(doc_vecs, axis=1)
        topk_idx = np.argsort(score)[::-1][:5]

        print('top %d questions similar to "%s"' % (5, question_))
        for idx in topk_idx:
            print('> %s\t%s' % ('%.1f' % score[idx], questions_list[idx]))
            yield questions_list[idx]


@login_required
def search(request):
    question_ = request.GET.get('question', '')

    questions = [q.name.replace('What', '') for q in Question.objects.all()]
    departments = Department.objects.all()

    print(questions)

    logged_in_user = User.objects.get(id=request.session['user_id'])
    user_questions = {
        q.id
        for q in Question.objects.filter(user_id=logged_in_user)
    }

    header = 'Search Results: ' + question_

    matched_questions = []
    for match in get_matches(questions, question_):
        qs = Question.objects.filter(name=match)
        matched_questions.extend([q for q in qs])

    return render(request, 'questions/questions.html', {
        'questions': matched_questions,
        'departments': departments,
        'header': header,
        'title': header,
        'logged_in_user': logged_in_user,
        'questions_upvoted': logged_in_user.question_upvotes(),
        'questions_downvoted': logged_in_user.question_downvotes(),
        'user_questions': user_questions
    })
