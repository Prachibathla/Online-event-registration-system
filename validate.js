/**
 * validate.js – Client-side validation for EventHub registration forms.
 * Works alongside HTML5 built-in validation and Bootstrap's
 * "was-validated" class pattern.
 */

(function () {
  'use strict';

  /**
   * Apply Bootstrap's was-validated class on submit to show
   * native invalid messages for any form that has the novalidate
   * attribute (i.e. our registration form).
   */
  document.addEventListener('DOMContentLoaded', function () {
    const forms = document.querySelectorAll('form[novalidate]');

    forms.forEach(function (form) {
      form.addEventListener('submit', function (event) {
        // Extra custom validations before the built-in check
        customValidate(form);

        if (!form.checkValidity()) {
          event.preventDefault();
          event.stopPropagation();
        }
        form.classList.add('was-validated');
      });
    });
  });

  /**
   * Custom validations beyond what HTML5 handles.
   * Sets custom validity messages on fields when needed.
   */
  function customValidate(form) {
    // Email format
    const emailField = form.querySelector('input[type="email"]');
    if (emailField) {
      const emailPattern = /^[\w.+-]+@[\w-]+\.[a-zA-Z]{2,}$/;
      if (emailField.value && !emailPattern.test(emailField.value)) {
        emailField.setCustomValidity('Please enter a valid email address.');
      } else {
        emailField.setCustomValidity('');
      }
    }

    // Phone format
    const phoneField = form.querySelector('input[type="tel"]');
    if (phoneField) {
      const phonePattern = /^\+?[\d\s\-]{7,15}$/;
      if (phoneField.value && !phonePattern.test(phoneField.value)) {
        phoneField.setCustomValidity(
          'Enter a valid phone number (7–15 digits, spaces or dashes allowed).'
        );
      } else {
        phoneField.setCustomValidity('');
      }
    }
  }

  /**
   * Clear custom validity on input so the user gets live feedback.
   */
  document.addEventListener('DOMContentLoaded', function () {
    document.querySelectorAll('input[type="email"], input[type="tel"]').forEach(function (field) {
      field.addEventListener('input', function () {
        field.setCustomValidity('');
      });
    });
  });
})();
